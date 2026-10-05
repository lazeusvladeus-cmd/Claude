"""Step-by-step progress reporting for long agent runs.

The dashboard runs each request as a background job and shows these steps live.
A context variable keeps the plumbing out of every function signature; `step()` is a
no-op when nothing is listening (CLI, tests).
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Callable, Optional

_reporter: ContextVar[Optional[Callable[[str], None]]] = ContextVar("vike_progress", default=None)


def set_reporter(fn: Optional[Callable[[str], None]]):
    return _reporter.set(fn)


def step(message: str) -> None:
    fn = _reporter.get()
    if fn is not None:
        fn(message)
