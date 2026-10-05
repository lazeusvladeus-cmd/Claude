"""Single shared-password login for the hosted dashboard (signed, HttpOnly cookie)."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from collections import defaultdict, deque

COOKIE = "vike_session"
TTL = 30 * 24 * 3600


class Auth:
    def __init__(self, password: str, secret: str = ""):
        self.password = password
        self.secret = (secret or secrets.token_hex(32)).encode()
        self.failures: dict[str, deque] = defaultdict(deque)

    @property
    def required(self) -> bool:
        return bool(self.password)

    def _sig(self, exp: int) -> str:
        # Bind the token to the password too, so changing APP_PASSWORD logs everyone out.
        return hmac.new(self.secret, f"{exp}:{self.password}".encode(), hashlib.sha256).hexdigest()

    def issue(self) -> str:
        exp = int(time.time()) + TTL
        return f"{exp}.{self._sig(exp)}"

    def valid(self, token: str | None) -> bool:
        if not self.required:
            return True
        if not token or "." not in token:
            return False
        exp_s, sig = token.split(".", 1)
        if not exp_s.isdigit() or int(exp_s) < time.time():
            return False
        return hmac.compare_digest(sig, self._sig(int(exp_s)))

    def throttled(self, ip: str) -> bool:
        q = self.failures[ip]
        while q and q[0] < time.time() - 900:
            q.popleft()
        return len(q) >= 10

    def check_password(self, ip: str, password: str) -> bool:
        ok = hmac.compare_digest(password.encode(), self.password.encode())
        if not ok:
            self.failures[ip].append(time.time())
        return ok
