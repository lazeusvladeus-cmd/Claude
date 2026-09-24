"""Image backends: Nano Banana via Gemini API (primary) and fal.ai (secondary)."""

from __future__ import annotations

import base64
import logging
import mimetypes
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Protocol

import httpx

from ..llm import LLMError, post_json

log = logging.getLogger(__name__)


class ImageGenerationError(RuntimeError):
    pass


@dataclass
class RefImage:
    data: bytes
    mime: str

    @classmethod
    def from_path(cls, p: Path) -> "RefImage":
        return cls(p.read_bytes(), mimetypes.guess_type(p.name)[0] or "image/png")

    def data_uri(self) -> str:
        return f"data:{self.mime};base64,{base64.b64encode(self.data).decode()}"


@dataclass
class ImageResult:
    data: bytes
    mime: str
    backend: str
    model: str


class ImageBackend(Protocol):
    name: str

    def available(self) -> bool: ...

    def generate(self, prompt: str, aspect_ratio: str, refs: list[RefImage]) -> ImageResult: ...


class NanoBananaBackend:
    """Gemini image models ("Nano Banana" / "Nano Banana Pro") via AI Studio or Vertex AI."""

    name = "nano-banana"

    def __init__(self, api_key: str, model: str, *, mode: str = "aistudio", vertex_project: str = "",
                 vertex_location: str = "global", http: Optional[httpx.Client] = None):
        self.api_key, self.model, self.mode = api_key, model, mode
        self.vertex_project, self.vertex_location = vertex_project, vertex_location
        self.http = http or httpx.Client()

    def available(self) -> bool:
        return bool(self.vertex_project) if self.mode == "vertex" else bool(self.api_key)

    def _endpoint(self) -> tuple[str, dict]:
        if self.mode == "vertex":
            token = subprocess.run(["gcloud", "auth", "print-access-token"], capture_output=True,
                                   text=True, check=True).stdout.strip()
            host = ("aiplatform.googleapis.com" if self.vertex_location == "global"
                    else f"{self.vertex_location}-aiplatform.googleapis.com")
            url = (f"https://{host}/v1/projects/{self.vertex_project}/locations/{self.vertex_location}"
                   f"/publishers/google/models/{self.model}:generateContent")
            return url, {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        return url, {"x-goog-api-key": self.api_key, "Content-Type": "application/json"}

    def generate(self, prompt: str, aspect_ratio: str, refs: list[RefImage]) -> ImageResult:
        parts: list[dict] = [{"inlineData": {"mimeType": r.mime, "data": base64.b64encode(r.data).decode()}}
                             for r in refs]
        if refs:
            prompt = ("The attached images are STYLE REFERENCES for the visual format only — match their "
                      "layout, realism and UI styling, but use only the content described below.\n\n" + prompt)
        parts.append({"text": prompt})
        payload = {
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {"responseModalities": ["TEXT", "IMAGE"],
                                 "imageConfig": {"aspectRatio": aspect_ratio}},
        }
        url, headers = self._endpoint()
        try:
            data = post_json(self.http, url, headers=headers, payload=payload, timeout=240)
        except LLMError as e:
            raise ImageGenerationError(str(e)) from e
        for cand in data.get("candidates", []) or []:
            for part in (cand.get("content") or {}).get("parts", []) or []:
                inline = part.get("inlineData") or part.get("inline_data")
                if inline and inline.get("data"):
                    return ImageResult(base64.b64decode(inline["data"]),
                                       inline.get("mimeType") or inline.get("mime_type") or "image/png",
                                       self.name, self.model)
        reason = (data.get("promptFeedback") or {}).get("blockReason") or \
            ((data.get("candidates") or [{}])[0].get("finishReason"))
        raise ImageGenerationError(f"Gemini returned no image (reason: {reason or 'unknown'})")


class FalBackend:
    """fal.ai hosted models. Uses the '/edit' variant when style references are attached."""

    name = "fal"

    def __init__(self, key: str, model: str, http: Optional[httpx.Client] = None):
        self.key, self.model = key, model
        self.http = http or httpx.Client()

    def available(self) -> bool:
        return bool(self.key)

    def generate(self, prompt: str, aspect_ratio: str, refs: list[RefImage]) -> ImageResult:
        model = self.model
        payload: dict = {"prompt": prompt, "num_images": 1, "aspect_ratio": aspect_ratio, "output_format": "png"}
        if refs and "nano-banana" in model:
            model = model.rstrip("/") + ("" if model.endswith("/edit") else "/edit")
            payload["image_urls"] = [r.data_uri() for r in refs]
            payload["prompt"] = ("The provided images are STYLE REFERENCES for the visual format only. "
                                 "Create a NEW image using only the content described here.\n\n" + prompt)
        headers = {"Authorization": f"Key {self.key}", "Content-Type": "application/json"}
        try:
            data = post_json(self.http, f"https://fal.run/{model}", headers=headers, payload=payload, timeout=300)
        except LLMError as e:
            raise ImageGenerationError(str(e)) from e
        images = data.get("images") or []
        if not images or not images[0].get("url"):
            raise ImageGenerationError("fal.ai returned no image")
        url = images[0]["url"]
        if url.startswith("data:"):
            header, b64 = url.split(",", 1)
            return ImageResult(base64.b64decode(b64), header[5:].split(";")[0], self.name, model)
        r = self.http.get(url, timeout=120)
        if r.status_code >= 400:
            raise ImageGenerationError(f"could not download fal.ai image: HTTP {r.status_code}")
        return ImageResult(r.content, images[0].get("content_type") or "image/png", self.name, model)


class ImageRouter:
    """Try backends in priority order (Nano Banana first, fal.ai second)."""

    def __init__(self, backends: list[ImageBackend]):
        self.backends = backends

    def generate(self, prompt: str, aspect_ratio: str, refs: list[RefImage],
                 prefer: Optional[str] = None) -> ImageResult:
        order = sorted(self.backends, key=lambda b: 0 if prefer and b.name == prefer else 1) \
            if prefer else list(self.backends)
        errors = []
        for b in order:
            if not b.available():
                errors.append(f"{b.name}: not configured")
                continue
            try:
                return b.generate(prompt, aspect_ratio, refs)
            except (ImageGenerationError, httpx.HTTPError, subprocess.CalledProcessError, FileNotFoundError) as e:
                log.warning("image backend %s failed: %s", b.name, e)
                errors.append(f"{b.name}: {e}")
        raise ImageGenerationError("all image backends failed — " + "; ".join(errors))
