import base64
import json

import httpx
import pytest

from conftest import PNG, FakeChat, FakeWeb, good_variant, make_orch
from vike_ads.images.backends import FalBackend, ImageGenerationError, NanoBananaBackend, RefImage
from vike_ads.llm import ChatClient, OpenAIClient
from vike_ads.search import MetaAdLibrary


def client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_gemini_payload_and_parse():
    seen = {}

    def handler(req):
        seen["url"], seen["key"], seen["body"] = str(req.url), req.headers["x-goog-api-key"], json.loads(req.content)
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [
            {"text": "here"}, {"inlineData": {"mimeType": "image/png", "data": base64.b64encode(PNG).decode()}}]}}]})

    b = NanoBananaBackend("k", "gemini-3-pro-image-preview", http=client(handler))
    out = b.generate("draw", "3:4", [RefImage(PNG, "image/png")])
    assert out.data == PNG and out.backend == "nano-banana"
    assert seen["url"].endswith("/v1beta/models/gemini-3-pro-image-preview:generateContent")
    assert seen["key"] == "k"
    cfg = seen["body"]["generationConfig"]
    assert cfg["imageConfig"]["aspectRatio"] == "3:4" and "IMAGE" in cfg["responseModalities"]
    parts = seen["body"]["contents"][0]["parts"]
    assert "inlineData" in parts[0] and "STYLE REFERENCES" in parts[-1]["text"]


def test_gemini_no_image_raises():
    b = NanoBananaBackend("k", "m", http=client(lambda r: httpx.Response(200, json={"promptFeedback": {"blockReason": "SAFETY"}})))
    with pytest.raises(ImageGenerationError, match="SAFETY"):
        b.generate("x", "1:1", [])


def test_fal_uses_edit_endpoint_with_refs_and_downloads():
    seen = []

    def handler(req):
        seen.append(req)
        if req.url.host == "fal.run":
            return httpx.Response(200, json={"images": [{"url": "https://cdn.fal.media/x.png", "content_type": "image/png"}]})
        return httpx.Response(200, content=PNG)

    b = FalBackend("fk", "fal-ai/nano-banana-pro", http=client(handler))
    out = b.generate("p", "4:3", [RefImage(PNG, "image/png")])
    assert out.data == PNG
    assert seen[0].url.path == "/fal-ai/nano-banana-pro/edit"
    assert seen[0].headers["authorization"] == "Key fk"
    body = json.loads(seen[0].content)
    assert body["image_urls"][0].startswith("data:image/png;base64,") and body["aspect_ratio"] == "4:3"


def test_chat_client_json_mode():
    def handler(req):
        body = json.loads(req.content)
        assert body["response_format"] == {"type": "json_object"} and body["model"] == "deepseek-chat"
        return httpx.Response(200, json={"choices": [{"message": {"content": '```json\n{"a": 1}\n```'}}]})

    assert ChatClient("deepseek", "k", "https://api.deepseek.com", "deepseek-chat", client(handler)).json("s", "u") == {"a": 1}


def test_openai_web_search_citations():
    def handler(req):
        assert req.url.path == "/v1/responses"
        assert json.loads(req.content)["tools"] == [{"type": "web_search"}]
        text = "Lo-fi ads are winning."
        return httpx.Response(200, json={"output": [
            {"type": "web_search_call"},
            {"type": "message", "content": [{"type": "output_text", "text": text, "annotations": [
                {"type": "url_citation", "url": "https://a.com", "title": "A", "start_index": 0, "end_index": len(text)}]}]}]})

    text, cites = OpenAIClient("openai", "k", "https://api.openai.com/v1", "gpt-5", client(handler)).web_search("q")
    assert cites == [{"url": "https://a.com", "title": "A", "snippet": "Lo-fi ads are winning."}]


def test_meta_ad_library_strips_token_from_urls():
    def handler(req):
        assert req.url.params["access_token"] == "SECRET"
        assert json.loads(req.url.params["ad_reached_countries"]) == ["IE"]
        return httpx.Response(200, json={"data": [{"id": "123", "page_name": "Acme", "ad_creative_bodies": ["Hi"],
                                                   "ad_snapshot_url": "https://x/?access_token=SECRET"}]})

    out = MetaAdLibrary("SECRET", ["IE"], client(handler)).search("dm")
    assert out[0].url == "https://www.facebook.com/ads/library/?id=123"
    assert "SECRET" not in out[0].model_dump_json()


def test_web_api_flow(brand, store, consents):
    from fastapi.testclient import TestClient
    from vike_ads.web.server import create_app

    openai = FakeChat("openai", {"senior creative strategist": {"concepts": [{"name": "N", "variants": [good_variant()]}]}})
    orch = make_orch(brand, store, consents, openai=openai, web=FakeWeb())
    api = TestClient(create_app(orch))
    r = api.post("/api/ask", json={"text": "give me an ad idea for dentists"}).json()
    assert r["kind"] == "concepts"
    v = r["concepts"][0]["variants"][0]
    assert api.get(v["image"]["url"]).content == PNG
    assert api.get("/images/..%2Fconsents.json").status_code == 404

    q = api.post("/api/image", json={"ref": v["id"], "photoreal_name": "Mary"}).json()
    assert q["kind"] == "question" and q["pending_name"] == "Mary"
    assert api.post("/api/consent", json={"name": "Mary", "confirmation": "yes"}).status_code == 400
    assert api.post("/api/consent", json={"name": "Mary", "confirmation": "yes, real client with consent"}).status_code == 200
    assert api.post("/api/image", json={"ref": v["id"], "photoreal_name": "Mary"}).json()["kind"] == "image"
    assert api.get("/").status_code == 200
