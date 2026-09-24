"""Lightweight local dashboard (FastAPI). Binds to 127.0.0.1 by default — it is a
single-user local tool with no authentication, so don't expose it publicly."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..guardrails import consent_question
from ..images.backends import ImageGenerationError
from ..llm import LLMError
from ..models import Concept, VisualFormat
from ..orchestrator import Orchestrator, Result

STATIC = Path(__file__).parent / "static"
CONSENT_PHRASE = "yes, real client with consent"


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
    backend: Optional[str] = None


class ConsentIn(BaseModel):
    name: str
    confirmation: str


def _concept_json(c: Concept) -> dict:
    d = c.model_dump(mode="json")
    for v in d["variants"]:
        if v.get("image"):
            v["image"]["url"] = f"/images/{Path(v['image']['path']).name}"
    return d


def _out(res: Result) -> dict:
    return {"kind": res.kind, "markdown": res.markdown, "question": res.question,
            "pending_name": res.pending_name, "notes": res.notes,
            "concepts": [_concept_json(c) for c in res.concepts]}


def create_app(orch: Orchestrator) -> FastAPI:
    app = FastAPI(title="Vike Ads", docs_url=None, redoc_url=None)

    def guarded(fn, *a, **kw) -> dict:
        try:
            return _out(fn(*a, **kw))
        except (RuntimeError, ValueError, LLMError, ImageGenerationError, httpx.HTTPError) as e:
            raise HTTPException(400, str(e))

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html")

    @app.get("/api/status")
    def status():
        return {"integrations": orch.settings.status(), "consent_phrase": CONSENT_PHRASE}

    # Sync endpoints run in FastAPI's threadpool, so long agent runs don't block the server.
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

    @app.post("/api/consent")
    def consent(body: ConsentIn):
        # Explicit, per-name confirmation — the typed phrase must match exactly.
        if body.confirmation.strip().lower() != CONSENT_PHRASE:
            raise HTTPException(400, f"Not confirmed. {consent_question(body.name)}")
        return orch.consents.confirm(body.name, confirmed_by="dashboard", note="confirmed in dashboard")

    @app.get("/api/concepts")
    def concepts():
        return [_concept_json(c) for c in orch.store.list_concepts()]

    @app.get("/api/research/latest")
    def latest():
        from ..render import report_md
        rep = orch.store.latest_report()
        return {"markdown": report_md(rep) if rep else "No research yet — run a research request.",
                "id": rep.id if rep else None}

    @app.get("/images/{name}")
    def images(name: str):
        path = (orch.store.images_dir / name).resolve()
        if path.parent != orch.store.images_dir.resolve() or not path.is_file():
            raise HTTPException(404)
        return FileResponse(path)

    return app


def serve(orch: Orchestrator, *, host: str, port: int, with_scheduler: bool = False) -> None:
    import uvicorn

    sched = None
    if with_scheduler:
        from ..scheduler import make_scheduler
        sched = make_scheduler(orch, blocking=False)
        sched.start()
    print(f"Vike Ads dashboard: http://{host}:{port}")
    try:
        uvicorn.run(create_app(orch), host=host, port=port, log_level="warning")
    finally:
        if sched:
            sched.shutdown(wait=False)
