"""Minimal OpenAI-compatible chat clients (OpenAI + DeepSeek) over plain HTTP.

Using httpx directly keeps the dependency surface small and lets both providers
share one code path (DeepSeek exposes an OpenAI-compatible API).
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Optional

import httpx

log = logging.getLogger(__name__)

RETRY_STATUS = {408, 409, 429, 500, 502, 503, 504}


class LLMError(RuntimeError):
    pass


def post_json(client: httpx.Client, url: str, *, headers: dict, payload: dict,
              attempts: int = 3, timeout: float = 180.0) -> dict:
    """POST with retry/backoff on transient failures. Raises LLMError on final failure."""
    last = ""
    for i in range(attempts):
        try:
            r = client.post(url, headers=headers, json=payload, timeout=timeout)
        except httpx.HTTPError as e:
            last = f"{type(e).__name__}: {e}"
        else:
            if r.status_code < 400:
                return r.json()
            last = f"HTTP {r.status_code}: {r.text[:500]}"
            if r.status_code not in RETRY_STATUS:
                break
        if i < attempts - 1:
            time.sleep(2 ** (i + 1))
    raise LLMError(f"{url} failed: {last}")


def parse_json_object(text: str) -> dict:
    """Parse a JSON object out of model output, tolerating ```json fences."""
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t
        t = t.rsplit("```", 1)[0]
    start, end = t.find("{"), t.rfind("}")
    if start == -1 or end == -1:
        raise LLMError(f"model did not return JSON: {text[:200]}")
    return json.loads(t[start:end + 1])


class ChatClient:
    """An OpenAI-compatible /chat/completions client that returns parsed JSON."""

    def __init__(self, name: str, api_key: str, base_url: str, model: str,
                 http: Optional[httpx.Client] = None):
        self.name = name
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.http = http or httpx.Client()

    @property
    def headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    def json(self, system: str, user: str | list[dict[str, Any]]) -> dict:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system + "\nRespond with a single JSON object only."},
                {"role": "user", "content": user},
            ],
            "response_format": {"type": "json_object"},
        }
        data = post_json(self.http, f"{self.base_url}/chat/completions",
                         headers=self.headers, payload=payload)
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise LLMError(f"{self.name}: unexpected response shape") from e
        try:
            return parse_json_object(content or "")
        except json.JSONDecodeError as e:
            raise LLMError(f"{self.name}: invalid JSON in response") from e


class OpenAIClient(ChatClient):
    """OpenAI client with the Responses API web_search tool for fresh web search."""

    def web_search(self, query: str) -> tuple[str, list[dict[str, str]]]:
        payload = {"model": self.model, "tools": [{"type": "web_search"}], "input": query}
        data = post_json(self.http, f"{self.base_url}/responses", headers=self.headers, payload=payload)
        text_parts: list[str] = []
        citations: list[dict[str, str]] = []
        seen: set[str] = set()
        for item in data.get("output", []) or []:
            if item.get("type") != "message":
                continue
            for c in item.get("content", []) or []:
                if c.get("type") != "output_text":
                    continue
                text = c.get("text", "")
                text_parts.append(text)
                for a in c.get("annotations", []) or []:
                    url = a.get("url")
                    if a.get("type") == "url_citation" and url and url not in seen:
                        seen.add(url)
                        s, e = a.get("start_index"), a.get("end_index")
                        snippet = text[max(0, s - 200):e] if isinstance(s, int) and isinstance(e, int) else ""
                        citations.append({"url": url, "title": a.get("title", ""), "snippet": snippet})
        return "\n".join(text_parts), citations
