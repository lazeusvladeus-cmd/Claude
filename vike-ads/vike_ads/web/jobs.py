"""In-process background jobs for the dashboard.

Agent runs take one to several minutes, longer than many hosting proxies keep a
request open. The dashboard starts a job, then polls it, showing each progress step
as it happens. Jobs live in memory; a restart forgets running jobs but never the
saved research, concepts or images.
"""

from __future__ import annotations

import logging
import secrets
import threading
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Optional

from ..progress import set_reporter

log = logging.getLogger(__name__)


@dataclass
class Job:
    id: str
    action: str
    label: str
    status: str = "queued"  # queued | running | done | error
    steps: list[dict] = field(default_factory=list)
    result: Optional[dict] = None
    error: Optional[str] = None
    created: float = field(default_factory=time.time)
    finished: Optional[float] = None

    def public(self) -> dict:
        return asdict(self)


class JobManager:
    def __init__(self, workers: int = 2, keep: int = 100):
        self.pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="vike-job")
        self.jobs: "OrderedDict[str, Job]" = OrderedDict()
        self.keep = keep
        self.lock = threading.Lock()

    def submit(self, action: str, label: str, fn: Callable[[], dict[str, Any]]) -> Job:
        job = Job(id=secrets.token_hex(6), action=action, label=label[:160])
        with self.lock:
            self.jobs[job.id] = job
            while len(self.jobs) > self.keep:
                self.jobs.popitem(last=False)
        self.pool.submit(self._run, job, fn)
        return job

    def _run(self, job: Job, fn: Callable[[], dict[str, Any]]) -> None:
        job.status = "running"
        set_reporter(lambda msg: job.steps.append({"at": time.time(), "text": msg}))
        try:
            job.result = fn()
            job.status = "done"
        except Exception as e:  # surfaced to the user as the job's error
            log.exception("job %s failed", job.id)
            job.error = str(e) or type(e).__name__
            job.status = "error"
        finally:
            set_reporter(None)
            job.finished = time.time()

    def get(self, job_id: str) -> Optional[Job]:
        return self.jobs.get(job_id)

    def recent(self, n: int = 20) -> list[Job]:
        return list(reversed(list(self.jobs.values())))[:n]
