import base64
import json
import time
from datetime import datetime, timedelta, timezone

import httpx
from fastapi.testclient import TestClient

from conftest import PNG, FakeChat, FakeWeb, good_variant, make_orch
from vike_ads.mirror import GitHubMirror, git_blob_sha
from vike_ads.models import ResearchReport
from vike_ads.store import Store
from vike_ads.web.server import create_app


class FakeGitHub:
    """Just enough of the GitHub REST API: repo info, recursive tree, blobs, contents PUT."""

    def __init__(self):
        self.files: dict[str, bytes] = {}
        self.puts = 0

    def handler(self, req: httpx.Request) -> httpx.Response:
        assert req.headers["authorization"] == "Bearer tok"
        path = req.url.path.removeprefix("/repos/acme/data")
        if req.method == "GET" and path == "":
            return httpx.Response(200, json={"default_branch": "main"})
        if req.method == "GET" and path == "/git/trees/main":
            if not self.files:
                return httpx.Response(409, json={"message": "Git Repository is empty."})
            return httpx.Response(200, json={"tree": [
                {"path": p, "type": "blob", "sha": git_blob_sha(d)} for p, d in self.files.items()]})
        if req.method == "GET" and path.startswith("/git/blobs/"):
            sha = path.rsplit("/", 1)[1]
            data = next(d for d in self.files.values() if git_blob_sha(d) == sha)
            return httpx.Response(200, json={"content": base64.b64encode(data).decode(), "encoding": "base64"})
        if req.method == "PUT" and path.startswith("/contents/"):
            rel = path.removeprefix("/contents/")
            body = json.loads(req.content)
            if rel in self.files and body.get("sha") != git_blob_sha(self.files[rel]):
                return httpx.Response(409, json={"message": "sha mismatch"})
            self.files[rel] = base64.b64decode(body["content"])
            self.puts += 1
            return httpx.Response(200, json={"content": {"sha": git_blob_sha(self.files[rel])}})
        if req.method == "GET" and path.startswith("/contents/"):
            rel = path.removeprefix("/contents/")
            if rel not in self.files:
                return httpx.Response(404)
            return httpx.Response(200, json={"sha": git_blob_sha(self.files[rel])})
        return httpx.Response(404, json={"message": f"unhandled {req.method} {path}"})


def mirror_for(gh, root):
    return GitHubMirror("acme/data", "tok", root, http=httpx.Client(transport=httpx.MockTransport(gh.handler)))


def test_round_trip_survives_a_wiped_disk(tmp_path, brand):
    gh = FakeGitHub()
    # First boot on an empty repo: nothing to load, then a run creates files.
    s1 = Store(tmp_path / "boot1")
    m1 = mirror_for(gh, s1.root)
    assert m1.pull() == 0
    s1.save_report(ResearchReport(id="r-1", topic="t"))
    (s1.images_dir / "c-1-A-1.png").write_bytes(PNG)
    (s1.root / "consents.json").write_text("{}")
    (s1.root / "weekly.log").write_text("not synced")
    assert m1.push() == 3
    assert set(gh.files) == {"research/r-1.json", "images/c-1-A-1.png", "consents.json"}
    assert m1.push() == 0  # unchanged files are not re-uploaded

    # Host sleeps, disk is wiped, app wakes on a fresh folder.
    s2 = Store(tmp_path / "boot2")
    m2 = mirror_for(gh, s2.root)
    assert m2.pull() == 2  # JSON restored immediately...
    assert s2.get_report("r-1") is not None
    assert not (s2.images_dir / "c-1-A-1.png").exists()  # ...images only when asked for
    assert m2.fetch("images/c-1-A-1.png").read_bytes() == PNG
    assert m2.fetch("images/missing.png") is None


def test_conflicting_write_overwrites_instead_of_failing(tmp_path):
    gh = FakeGitHub()
    gh.files["consents.json"] = b'{"old": 1}'
    s = Store(tmp_path / "d")
    m = mirror_for(gh, s.root)
    m.pull()
    gh.files["consents.json"] = b'{"changed elsewhere": 1}'  # another writer got there first
    (s.root / "consents.json").write_text('{"mine": 1}')
    assert m.push() == 1 and gh.files["consents.json"] == b'{"mine": 1}'


def test_dashboard_syncs_after_runs_and_restores_images(tmp_path, brand, store, consents):
    gh = FakeGitHub()
    openai = FakeChat("openai", {"senior creative strategist": {"concepts": [{"name": "N", "variants": [good_variant()]}]}})
    orch = make_orch(brand, store, consents, openai=openai, web=FakeWeb())
    orch.mirror = mirror_for(gh, store.root)
    with TestClient(create_app(orch)) as api:
        job = api.post("/api/jobs", json={"action": "idea", "text": "preschools", "variants": 1}).json()
        for _ in range(200):
            j = api.get(f"/api/jobs/{job['id']}").json()
            if j["status"] in {"done", "error"}:
                break
            time.sleep(0.02)
        assert j["status"] == "done", j
        assert any(p.startswith("concepts/") for p in gh.files) and any(p.startswith("images/") for p in gh.files)
        url = j["result"]["concepts"][0]["variants"][0]["image"]["url"]
        for p in store.images_dir.iterdir():  # simulate the free tier wiping the disk
            p.unlink()
        orch.mirror.pull()
        assert api.get(url).content == PNG


def test_catch_up_research_runs_when_a_week_was_missed(brand, store, consents):
    from vike_ads.scheduler import research_is_due
    orch = make_orch(brand, store, consents)
    assert research_is_due(orch)
    store.save_report(ResearchReport(id="r-old", topic="t", created_at=datetime.now(timezone.utc) - timedelta(days=8)))
    assert research_is_due(orch)
    store.save_report(ResearchReport(id="r-new", topic="t"))
    assert not research_is_due(orch)


def test_bad_token_fails_with_a_clear_message(tmp_path):
    import pytest
    from vike_ads.mirror import MirrorError
    m = GitHubMirror("acme/data", "tok", tmp_path, http=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(401))))
    with pytest.raises(MirrorError, match="VIKE_GITHUB_TOKEN"):
        m.pull()
