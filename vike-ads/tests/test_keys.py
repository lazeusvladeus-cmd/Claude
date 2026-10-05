import httpx
import pytest

from conftest import FakeWeb, make_orch
from vike_ads.config import Settings
from vike_ads.llm import LLMError, post_json


def test_org_id_in_place_of_api_key_is_flagged():
    w = Settings(openai_api_key="org-RhRKabcdefghihGE").key_warnings()
    assert "organization ID" in w["openai"]
    assert Settings(openai_api_key="sk-proj-abc").key_warnings() == {}
    assert "owner/repo" in Settings(github_store_repo="https://github.com/a/b.git").key_warnings()["github storage"]


def test_auth_errors_name_the_setting_to_fix_and_dont_retry():
    calls = []

    def handler(req):
        calls.append(req)
        return httpx.Response(401, json={"error": {"code": "invalid_api_key"}})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(LLMError, match="OPENAI_API_KEY.*Environment tab"):
        post_json(http, "https://api.openai.com/v1/chat/completions", headers={}, payload={})
    assert len(calls) == 1


def test_identical_search_failures_collapse_to_one_note(brand, store, consents):
    class BadKeyWeb(FakeWeb):
        def search(self, query, n=5):
            raise LLMError("OpenAI rejected the API key (HTTP 401).")

    orch = make_orch(brand, store, consents, web=BadKeyWeb())
    rep = orch.research("cafes").report
    assert any(n.startswith("All 11 web searches failed: OpenAI rejected the API key") for n in rep.notes)
    assert not any(n.startswith("search failed for") for n in rep.notes)


def test_status_endpoint_reports_key_warnings(brand, store, consents):
    from fastapi.testclient import TestClient
    from vike_ads.web.server import create_app
    orch = make_orch(brand, store, consents)
    orch.settings.openai_api_key = "org-123"
    body = TestClient(create_app(orch)).get("/api/status").json()
    assert "openai" in body["warnings"]
