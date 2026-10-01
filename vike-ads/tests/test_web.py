import time

import pytest
from fastapi.testclient import TestClient

from conftest import FakeChat, FakeWeb, good_variant, make_orch
from vike_ads.web.auth import Auth
from vike_ads.web.server import create_app, serve


def ideas_openai():
    return FakeChat("openai", {"senior creative strategist": {"concepts": [{"name": "N", "variants": [good_variant()]}]}})


def wait(api, job_id, timeout=5):
    end = time.time() + timeout
    while time.time() < end:
        job = api.get(f"/api/jobs/{job_id}").json()
        if job["status"] in {"done", "error"}:
            return job
        time.sleep(0.02)
    raise AssertionError("job did not finish")


def test_job_reports_live_steps_and_result(brand, store, consents):
    orch = make_orch(brand, store, consents, openai=ideas_openai(), web=FakeWeb())
    api = TestClient(create_app(orch))
    job = api.post("/api/jobs", json={"action": "idea", "text": "preschools in Lviv", "variants": 1}).json()
    done = wait(api, job["id"])
    assert done["status"] == "done", done["error"]
    texts = [s["text"] for s in done["steps"]]
    assert any(t.startswith("Writing 1 concept") for t in texts)
    assert any(t.startswith("Checking variant A") for t in texts)
    assert any(t.startswith("Generating with nano-banana") for t in texts)
    v = done["result"]["concepts"][0]["variants"][0]
    assert v["image"]["url"].startswith("images/") and "prompt" not in v["image"] and "path" not in v["image"]


def test_job_errors_are_reported(brand, store, consents):
    orch = make_orch(brand, store, consents)  # no OpenAI key
    api = TestClient(create_app(orch))
    job = api.post("/api/jobs", json={"action": "idea", "text": "x"}).json()
    done = wait(api, job["id"])
    assert done["status"] == "error" and "OPENAI_API_KEY" in done["error"]
    assert api.post("/api/jobs", json={"action": "idea", "text": " "}).status_code == 400
    assert api.get("/api/jobs/nope").status_code == 404


def test_password_protects_everything_but_login(brand, store, consents):
    orch = make_orch(brand, store, consents, openai=ideas_openai(), web=FakeWeb())
    api = TestClient(create_app(orch, auth=Auth("s3cret", "k")))
    assert api.get("/").status_code == 200
    assert api.get("/healthz").status_code == 200
    assert api.get("/api/session").json() == {"auth_required": True, "authenticated": False}
    for path in ("/api/concepts", "/api/status", "/api/consents", "/images/x.png"):
        assert api.get(path).status_code == 401
    assert api.post("/api/jobs", json={"action": "research"}).status_code == 401
    assert api.post("/api/login", json={"password": "wrong"}).status_code == 401
    assert api.post("/api/login", json={"password": "s3cret"}).status_code == 200
    assert api.get("/api/session").json()["authenticated"] is True
    assert api.get("/api/concepts").status_code == 200
    api.post("/api/logout")
    assert api.get("/api/concepts").status_code == 401


def test_login_is_throttled(brand, store, consents):
    api = TestClient(create_app(make_orch(brand, store, consents), auth=Auth("pw")))
    for _ in range(10):
        api.post("/api/login", json={"password": "nope"})
    assert api.post("/api/login", json={"password": "pw"}).status_code == 429


def test_forged_or_expired_cookie_rejected():
    a = Auth("pw", "secret")
    tok = a.issue()
    assert a.valid(tok)
    exp, sig = tok.split(".")
    assert not a.valid(f"{int(exp) + 1}.{sig}")
    assert not a.valid(f"1.{sig}")
    assert not Auth("other-password", "secret").valid(tok)


def test_refuses_public_bind_without_password(brand, store, consents):
    orch = make_orch(brand, store, consents)
    with pytest.raises(SystemExit, match="APP_PASSWORD"):
        serve(orch, host="0.0.0.0", port=0)


def test_page_is_served_with_document_shell(brand, store, consents):
    api = TestClient(create_app(make_orch(brand, store, consents)))
    html = api.get("/").text
    assert html.startswith("<!doctype html>") and "<title>Vike Ads Studio</title>" in html
