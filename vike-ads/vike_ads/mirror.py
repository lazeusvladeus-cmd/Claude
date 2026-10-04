"""Keep the data folder in a private GitHub repo, so free hosts with throwaway disks
(Render free, which wipes files whenever it sleeps) lose nothing.

  * On start: download the research, concept and consent JSON (small, needed at once).
    Images are fetched lazily the first time the dashboard asks for one.
  * After every run, consent change and on shutdown: commit whatever changed.
  * Last writer wins if the CLI and the hosted app edit the same file.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import threading
from pathlib import Path
from typing import Optional

import httpx

log = logging.getLogger(__name__)

API = "https://api.github.com"
SYNCED_DIRS = ("research", "concepts", "images")
SYNCED_FILES = ("consents.json",)


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


class MirrorError(RuntimeError):
    pass


class GitHubMirror:
    def __init__(self, repo: str, token: str, root: Path, http: Optional[httpx.Client] = None):
        if repo.count("/") != 1:
            raise ValueError("VIKE_GITHUB_STORE must look like owner/repo")
        self.repo, self.token, self.root = repo, token, Path(root)
        self.http = http or httpx.Client(timeout=60)
        self.remote: dict[str, str] = {}  # relative path -> blob sha on GitHub
        self.lock = threading.Lock()
        self._stop = threading.Event()

    @property
    def headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}", "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28"}

    def _get(self, path: str) -> httpx.Response:
        return self.http.get(f"{API}/repos/{self.repo}{path}", headers=self.headers)

    @staticmethod
    def synced(rel: str) -> bool:
        return rel in SYNCED_FILES or (rel.split("/", 1)[0] in SYNCED_DIRS and "/" in rel)

    # ------------------------------------------------------------------ download
    def pull(self) -> int:
        """Load the remote file list and download every non-image file. Returns files written."""
        r = self._get("")
        if r.status_code in (401, 403, 404):
            raise MirrorError(f"GitHub storage: can't open {self.repo} (HTTP {r.status_code}). Check VIKE_GITHUB_STORE "
                              "and that VIKE_GITHUB_TOKEN has Contents read/write on that repo.")
        r.raise_for_status()
        branch = r.json().get("default_branch", "main")
        t = self._get(f"/git/trees/{branch}?recursive=1")
        if t.status_code in (404, 409):  # empty repository: nothing to load yet
            return 0
        t.raise_for_status()
        self.remote = {e["path"]: e["sha"] for e in t.json().get("tree", [])
                       if e.get("type") == "blob" and self.synced(e["path"])}
        written = 0
        for rel, sha in self.remote.items():
            if rel.startswith("images/"):
                continue  # fetched on demand
            local = self.root / rel
            if local.exists() and git_blob_sha(local.read_bytes()) == sha:
                continue
            self._download(rel, sha)
            written += 1
        return written

    def _download(self, rel: str, sha: str) -> Path:
        r = self._get(f"/git/blobs/{sha}")
        r.raise_for_status()
        data = base64.b64decode(r.json()["content"])
        local = self.root / rel
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_bytes(data)
        return local

    def fetch(self, rel: str) -> Optional[Path]:
        """Download one file (an image) if GitHub has it and it's missing locally."""
        local = self.root / rel
        if local.exists():
            return local
        sha = self.remote.get(rel)
        if not sha:
            return None
        try:
            return self._download(rel, sha)
        except httpx.HTTPError as e:
            log.warning("could not fetch %s from GitHub: %s", rel, e)
            return None

    # ------------------------------------------------------------------ upload
    def _local_files(self) -> list[str]:
        out = []
        for p in self.root.rglob("*"):
            if p.is_file():
                rel = p.relative_to(self.root).as_posix()
                if self.synced(rel):
                    out.append(rel)
        return sorted(out)

    def _put(self, rel: str, data: bytes) -> str:
        body = {"message": f"vike-ads: update {rel}", "content": base64.b64encode(data).decode()}
        if rel in self.remote:
            body["sha"] = self.remote[rel]
        url = f"{API}/repos/{self.repo}/contents/{rel}"
        r = self.http.put(url, headers=self.headers, json=body)
        if r.status_code in (409, 422):  # someone else changed it: take their sha, overwrite once
            cur = self.http.get(url, headers=self.headers)
            if cur.status_code == 200:
                body["sha"] = cur.json()["sha"]
            else:
                body.pop("sha", None)
            r = self.http.put(url, headers=self.headers, json=body)
        if r.status_code >= 400:
            raise MirrorError(f"GitHub rejected {rel}: HTTP {r.status_code} {r.text[:200]}")
        return r.json()["content"]["sha"]

    def push(self) -> int:
        """Commit every local file that differs from GitHub. Returns files pushed."""
        with self.lock:
            pushed = 0
            for rel in self._local_files():
                data = (self.root / rel).read_bytes()
                sha = git_blob_sha(data)
                if self.remote.get(rel) == sha:
                    continue
                try:
                    self.remote[rel] = self._put(rel, data)
                    pushed += 1
                except (MirrorError, httpx.HTTPError) as e:
                    log.warning("GitHub sync failed for %s: %s", rel, e)
            if pushed:
                log.info("synced %d file(s) to %s", pushed, self.repo)
            return pushed

    def safe_push(self) -> None:
        try:
            self.push()
        except Exception:  # sync must never break a run; the next sync retries
            log.exception("GitHub sync failed")

    def start(self, interval: float = 60.0) -> None:
        """Background safety net: push changes every `interval` seconds."""
        def loop():
            while not self._stop.wait(interval):
                self.safe_push()
        threading.Thread(target=loop, name="vike-github-sync", daemon=True).start()

    def stop(self) -> None:
        self._stop.set()
        self.safe_push()
