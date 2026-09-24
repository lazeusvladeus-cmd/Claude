"""Command-line interface.

  vike-ads "give me an ad idea for dental clinics in Lviv"   # free text -> orchestrator
  vike-ads research ["topic"] [--themes fake_dm,anti_ad]
  vike-ads idea "request" [--variants 3] [--concepts 1] [--format review_card] [--no-images]
  vike-ads image <concept-or-variant-id | description> [--photoreal "Name"] [--backend fal]
  vike-ads list | show <id> | latest-research
  vike-ads consent add "Name" | consent list
  vike-ads serve [--port 8765] [--with-scheduler]
  vike-ads schedule            # blocking weekly research refresh
  vike-ads doctor              # which integrations are configured
"""

from __future__ import annotations

import argparse
import logging
import sys

from .config import Settings
from .models import VisualFormat
from .orchestrator import Orchestrator, Result, build
from .render import concept_list_md, concept_md, report_md

COMMANDS = {"ask", "research", "idea", "image", "list", "show", "latest-research", "consent", "serve",
            "schedule", "doctor"}


def _emit(res: Result) -> int:
    print(res.markdown)
    for n in res.notes:
        print(f"note: {n}", file=sys.stderr)
    return 0 if res.kind not in {"error"} else 1


def _confirm_consent(orch: Orchestrator, name: str) -> bool:
    """Ask the user — explicitly, per name — before any photo-realistic named likeness."""
    from .guardrails import consent_question
    if not sys.stdin.isatty():
        print(f"question: {consent_question(name)}\nRe-run interactively or use: vike-ads consent add \"{name}\"",
              file=sys.stderr)
        return False
    print(consent_question(name))
    ans = input('Type "yes, real client with consent" to confirm, anything else to cancel: ').strip().lower()
    if ans != "yes, real client with consent":
        print("Cancelled — keeping the placeholder identity.")
        return False
    orch.consents.confirm(name, confirmed_by="cli", note="confirmed interactively")
    return True


def _run_image(orch: Orchestrator, ref: str, photoreal: str | None, backend: str | None) -> int:
    res = orch.image(ref, photoreal_name=photoreal, backend=backend)
    if res.kind == "question" and res.pending_name:
        if not _confirm_consent(orch, res.pending_name):
            return 2
        res = orch.image(ref, photoreal_name=photoreal, backend=backend)
    return _emit(res)


def _formats(raw: str | None) -> list[VisualFormat] | None:
    if not raw:
        return None
    return [VisualFormat(x.strip()) for x in raw.split(",") if x.strip()]


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] not in COMMANDS and not argv[0].startswith("-"):
        argv = ["ask", " ".join(argv)]

    p = argparse.ArgumentParser(prog="vike-ads", description="Vike Marketing ad creative system")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd")

    a = sub.add_parser("ask", help="free-text request, routed by the orchestrator")
    a.add_argument("text")
    a.add_argument("--photoreal")

    r = sub.add_parser("research", help="research current ad creative trends")
    r.add_argument("topic", nargs="?", default="")
    r.add_argument("--themes", help="comma list: one_star_review,fake_dm,dashboard,anti_ad,authenticity")

    i = sub.add_parser("idea", help="full 4-part ad concepts (renders images unless --no-images)")
    i.add_argument("request")
    i.add_argument("--variants", type=int, default=3)
    i.add_argument("--concepts", type=int, default=1)
    i.add_argument("--format", help="comma list: dashboard,review_card,dm_screenshot")
    i.add_argument("--no-images", action="store_true")

    g = sub.add_parser("image", help="render part 4 only for an existing concept/variant")
    g.add_argument("ref", nargs="+")
    g.add_argument("--photoreal", help="real, consented client name for a photo-realistic avatar")
    g.add_argument("--backend", choices=["nano-banana", "fal"])

    sub.add_parser("list", help="list stored concepts")
    s = sub.add_parser("show", help="show a stored concept (4-part output)")
    s.add_argument("id")
    sub.add_parser("latest-research", help="print the latest research report")

    c = sub.add_parser("consent", help="record/list real-client likeness consent")
    c.add_argument("action", choices=["add", "list"])
    c.add_argument("name", nargs="?")

    w = sub.add_parser("serve", help="local web dashboard")
    w.add_argument("--host")
    w.add_argument("--port", type=int)
    w.add_argument("--with-scheduler", action="store_true")

    sub.add_parser("schedule", help="run the weekly research refresh (blocking)")
    sub.add_parser("doctor", help="show which integrations are configured")

    args = p.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.WARNING,
                        format="%(levelname)s %(name)s: %(message)s")
    if not args.cmd:
        p.print_help()
        return 0

    settings = Settings.from_env()
    if args.cmd == "doctor":
        for k, ok in settings.status().items():
            print(f"{'✓' if ok else '✗'} {k}")
        print(f"data dir: {settings.data_dir}\nbrand file: {settings.brand_file}")
        return 0

    orch = build(settings)
    try:
        if args.cmd == "ask":
            res = orch.handle(args.text, photoreal_name=args.photoreal)
            if res.kind == "question" and res.pending_name:
                if not _confirm_consent(orch, res.pending_name):
                    return 2
                res = orch.handle(args.text, photoreal_name=args.photoreal)
            return _emit(res)
        if args.cmd == "research":
            themes = [t.strip() for t in args.themes.split(",")] if args.themes else None
            return _emit(orch.research(args.topic, themes))
        if args.cmd == "idea":
            return _emit(orch.idea(args.request, n_concepts=args.concepts, n_variants=args.variants,
                                   formats=_formats(args.format), render_images=not args.no_images))
        if args.cmd == "image":
            return _run_image(orch, " ".join(args.ref), args.photoreal, args.backend)
        if args.cmd == "list":
            print(concept_list_md(orch.store.list_concepts()))
            return 0
        if args.cmd == "show":
            matches, _ = orch.store.find_variants(args.id)
            if not matches:
                print(f"not found: {args.id}", file=sys.stderr)
                return 1
            c = matches[0][0]
            wanted = {v.id for _, v in matches}
            print(concept_md(c.model_copy(update={"variants": [v for v in c.variants if v.id in wanted]})))
            return 0
        if args.cmd == "latest-research":
            rep = orch.store.latest_report()
            print(report_md(rep) if rep else "No research yet. Run: vike-ads research")
            return 0
        if args.cmd == "consent":
            if args.action == "list":
                for rec in orch.consents.all():
                    print(f"- {rec['name']} (confirmed {rec['confirmed_at']} via {rec['confirmed_by']})")
                return 0
            if not args.name:
                print("usage: vike-ads consent add \"Client Name\"", file=sys.stderr)
                return 1
            return 0 if _confirm_consent(orch, args.name) else 2
        if args.cmd == "serve":
            from .web.server import serve
            serve(orch, host=args.host or settings.web_host, port=args.port or settings.web_port,
                  with_scheduler=args.with_scheduler)
            return 0
        if args.cmd == "schedule":
            from .scheduler import make_scheduler
            print(f"Weekly research: every {settings.weekly_research_day} at {settings.weekly_research_hour}:00 "
                  f"({settings.timezone}). Ctrl+C to stop.")
            make_scheduler(orch, blocking=True).start()
            return 0
    except (RuntimeError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
