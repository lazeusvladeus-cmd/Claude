"""Dashboard server (FastAPI).

Local by default (127.0.0.1, no login). To host it, set APP_PASSWORD: every API call
and image then needs a signed session cookie, and the server refuses to listen on a
public interface without a password.
"""

from __future__ import annotations

import ipaddress
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal, Optional

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel

from .. import __version__
from ..agents.research import TREND_THEMES
from ..guardrails import consent_question
from ..images.backends import ImageGenerationError
from ..llm import LLMError
from ..models import Concept, ResearchReport, VisualFormat
from ..orchestrator import Orchestrator, Result
from .auth import COOKIE, TTL, Auth
from .jobs import JobManager

log = logging.getLogger(__name__)
STATIC = Path(__file__).parent / "static"
CONSENT_PHRASE = "yes, real client with consent"
PUBLIC_PATHS = {"/", "/healthz", "/api/session", "/api/login", "/api/logout"}

# app.html is written as a page fragment (it doubles as the published preview), so the
# server adds the document shell.
SHELL = ('<!doctype html><html lang="en"><meta charset="utf-8">'
         '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n')


class AskIn(BaseModel):
    text: str
    photoreal_name: Optional[str] = None


class ResearchIn(BaseModel):
    topic: str = ""
    themes: Optional[list[str]] = None


class IdeaIn(BaseModel):
    request: str
    variants: int = 3
    concepts: int = 1
    formats: Optional[list[VisualFormat]] = None
    render_images: bool = True


class ImageIn(BaseModel):
    ref: str
    photoreal_name: Optional[str] = None
    backend: Optional[Literal["nano-banana", "fal"]] = None


class JobIn(BaseModel):
    action: Literal["ask", "research", "idea", "image"]
    text: str = ""
    themes: Optional[list[str]] = None
    variants: int = 3
    concepts: int = 1
    formats: Optional[list[VisualFormat]] = None
    render_images: bool = True
    photoreal_name: Optional[str] = None
    backend: Optional[Literal["nano-banana", "fal"]] = None


class ConsentIn(BaseModel):
    name: str
    confirmation: str


class LoginIn(BaseModel):
    password: str


def _concept_json(c: Concept) -> dict:
    d = c.model_dump(mode="json")
    for v in d["variants"]:
        if v.get("image"):
            v["image"]["url"] = f"images/{Path(v['image']['path']).name}"
            v["image"].pop("prompt", None)
            v["image"].pop("path", None)
    return d


def _report_json(r: ResearchReport) -> dict:
    return r.model_dump(mode="json")


def _out(res: Result) -> dict:
    return {"kind": res.kind, "markdown": res.markdown, "question": res.question,
            "pending_name": res.pending_name, "notes": res.notes,
            "concepts": [_concept_json(c) for c in res.concepts],
            "report": _report_json(res.report) if res.report else None}


def create_app(orch: Orchestrator, *, auth: Optional[Auth] = None) -> FastAPI:
    auth = auth or Auth(orch.settings.app_password, orch.settings.app_secret)
    jobs = JobManager()
    mirror = orch.mirror

    def synced(fn):
        """Run fn, then commit new files to GitHub storage (free hosts wipe their disk)."""
        def run():
            try:
                return fn()
            finally:
                if mirror is not None:
                    mirror.safe_push()
        return run

    @asynccontextmanager
    async def lifespan(_app):
        if mirror is not None:
            mirror.start(interval=60)
        if orch.settings.web_scheduler:
            from ..scheduler import research_is_due
            if research_is_due(orch):
                log.info("weekly research is due (host may have been asleep): starting it now")
                jobs.submit("research", "Weekly research (catch-up)",
                            synced(lambda: _out(orch.research(orch.settings.weekly_research_topic))))
        yield
        if mirror is not None:
            mirror.stop()

    app = FastAPI(title="Vike Ads", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)

    @app.middleware("http")
    async def require_login(request: Request, call_next):
        if auth.required and request.url.path not in PUBLIC_PATHS and not auth.valid(request.cookies.get(COOKIE)):
            return JSONResponse({"detail": "Sign in to continue."}, status_code=401)
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        return response

    def guarded(fn, *a, **kw) -> dict:
        try:
            return _out(fn(*a, **kw))
        except (RuntimeError, ValueError, LLMError, ImageGenerationError, httpx.HTTPError) as e:
            raise HTTPException(400, str(e))

    # ---------------------------------------------------------------- page + session
    @app.get("/", response_class=HTMLResponse)
    def index():
        return SHELL + (STATIC / "app.html").read_text(encoding="utf-8")

    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    @app.get("/api/session")
    def session(request: Request):
        return {"auth_required": auth.required, "authenticated": auth.valid(request.cookies.get(COOKIE))}

    @app.post("/api/login")
    def login(body: LoginIn, request: Request):
        ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip() or \
            (request.client.host if request.client else "?")
        if not auth.required:
            return {"ok": True}
        if auth.throttled(ip):
            raise HTTPException(429, "Too many attempts. Wait 15 minutes and try again.")
        if not auth.check_password(ip, body.password):
            raise HTTPException(401, "That password didn't match.")
        resp = JSONResponse({"ok": True})
        https = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
        resp.set_cookie(COOKIE, auth.issue(), max_age=TTL, httponly=True, samesite="lax", secure=https)
        return resp

    @app.post("/api/logout")
    def logout():
        resp = JSONResponse({"ok": True})
        resp.delete_cookie(COOKIE)
        return resp

    # ---------------------------------------------------------------- read
    @app.get("/api/status")
    def status():
        s = orch.settings
        return {
            "version": __version__,
            "integrations": s.status(),
            "warnings": s.key_warnings(),
            "consent_phrase": CONSENT_PHRASE,
            "themes": {k: v["label"] for k, v in TREND_THEMES.items()},
            "schedule": {"enabled": s.web_scheduler, "day": s.weekly_research_day,
                         "hour": s.weekly_research_hour, "timezone": s.timezone},
            "models": {"copy": s.openai_model, "images": s.gemini_image_model, "fallback_images": s.fal_model},
        }

    @app.get("/api/brand")
    def brand():
        return orch.brand.raw

    @app.get("/api/concepts")
    def concepts():
        return [_concept_json(c) for c in orch.store.list_concepts()]

    @app.get("/api/research/latest")
    def latest():
        rep = orch.store.latest_report()
        return {"report": _report_json(rep) if rep else None}

    @app.get("/api/research")
    def research_list():
        return [{"id": r.id, "topic": r.topic, "created_at": r.created_at.isoformat(),
                 "findings": len(r.findings)} for r in orch.store.list_reports()[:20]]

    @app.get("/api/research/{rid}")
    def research_get(rid: str):
        rep = orch.store.get_report(rid) if rid.replace("-", "").isalnum() else None
        if rep is None:
            raise HTTPException(404, "No research report with that ID.")
        return {"report": _report_json(rep)}

    @app.get("/api/consents")
    def consents():
        return orch.consents.all()

    @app.post("/api/consent")
    def consent(body: ConsentIn):
        # Explicit, per-name confirmation; the typed phrase must match exactly.
        if body.confirmation.strip().lower() != CONSENT_PHRASE:
            raise HTTPException(400, f"Not confirmed. {consent_question(body.name)}")
        try:
            rec = orch.consents.confirm(body.name, confirmed_by="dashboard", note="confirmed in dashboard")
        except ValueError as e:
            raise HTTPException(400, str(e))
        if mirror is not None:
            mirror.safe_push()
        return rec

    # ---------------------------------------------------------------- background jobs
    @app.post("/api/jobs")
    def start_job(body: JobIn):
        text = body.text.strip()
        if body.action in {"ask", "idea", "image"} and not text:
            raise HTTPException(400, "Type a request first.")
        if body.action == "ask":
            fn = lambda: _out(orch.handle(text, photoreal_name=body.photoreal_name))  # noqa: E731
        elif body.action == "research":
            fn = lambda: _out(orch.research(text, body.themes))  # noqa: E731
        elif body.action == "idea":
            fn = lambda: _out(orch.idea(text, n_concepts=max(1, min(body.concepts, 3)),  # noqa: E731
                                        n_variants=max(1, min(body.variants, 6)), formats=body.formats,
                                        render_images=body.render_images))
        else:
            fn = lambda: _out(orch.image(text, photoreal_name=body.photoreal_name, backend=body.backend))  # noqa: E731
        return jobs.submit(body.action, text or "Ad creative trends", synced(fn)).public()

    @app.get("/api/jobs")
    def list_jobs():
        return [{k: v for k, v in j.public().items() if k != "result"} for j in jobs.recent()]

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str):
        job = jobs.get(job_id)
        if job is None:
            raise HTTPException(404, "That run is no longer available (the server may have restarted).")
        return job.public()

    # ---------------------------------------------------------------- synchronous API (scripts)
    @app.post("/api/ask")
    def ask(body: AskIn):
        return guarded(orch.handle, body.text, photoreal_name=body.photoreal_name)

    @app.post("/api/research")
    def research(body: ResearchIn):
        return guarded(orch.research, body.topic, body.themes)

    @app.post("/api/idea")
    def idea(body: IdeaIn):
        return guarded(orch.idea, body.request, n_concepts=body.concepts, n_variants=body.variants,
                       formats=body.formats, render_images=body.render_images)

    @app.post("/api/image")
    def image(body: ImageIn):
        return guarded(orch.image, body.ref, photoreal_name=body.photoreal_name, backend=body.backend)

    @app.get("/images/{name}")
    def images(name: str):
        path = (orch.store.images_dir / name).resolve()
        if path.parent != orch.store.images_dir.resolve():
            raise HTTPException(404)
        if not path.is_file() and mirror is not None:
            mirror.fetch(f"images/{name}")  # lazily restore images after a free-tier restart
        if not path.is_file():
            raise HTTPException(404)
        return FileResponse(path, headers={"Cache-Control": "private, max-age=86400"})

    app.state.jobs = jobs
    return app


def _is_loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def serve(orch: Orchestrator, *, host: str, port: int, with_scheduler: bool = False) -> None:
    import uvicorn

    if not _is_loopback(host) and not orch.settings.app_password:
        raise SystemExit("Refusing to listen on a public address without APP_PASSWORD. "
                         "Set APP_PASSWORD (anyone with the URL could otherwise spend your API credits).")
    sched = None
    if with_scheduler or orch.settings.web_scheduler:
        from ..scheduler import make_scheduler
        sched = make_scheduler(orch, blocking=False)
        sched.start()
    for name, msg in orch.settings.key_warnings().items():
        print(f"WARNING {name}: {msg}")
    print(f"Vike Ads Studio: http://{host}:{port}" + ("  (password required)" if orch.settings.app_password else ""))
    try:
        uvicorn.run(create_app(orch), host=host, port=port, log_level="warning", proxy_headers=True,
                    forwarded_allow_ips="*")
    finally:
        if sched:
            sched.shutdown(wait=False)
