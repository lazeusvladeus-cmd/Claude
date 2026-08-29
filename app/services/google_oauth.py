"""Shared Google OAuth user-credential loading, used by both Sheets and Calendar.

One authorization (scripts/google_oauth_setup.py, run once) covers both — this
avoids needing a service-account key file, which Google Cloud now blocks key
creation for by default on many accounts/organizations
(iam.disableServiceAccountKeyCreation). Signing in as yourself also means the
Sheet just needs to be yours — no "share with a robot email" step.
"""
from __future__ import annotations

from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from app.config import settings

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/calendar.readonly",
]


class GoogleAuthNotConfigured(RuntimeError):
    pass


def load_credentials() -> Credentials:
    token_path = Path(settings.google_token_file)
    if not token_path.exists():
        raise GoogleAuthNotConfigured(
            "Google isn't connected yet. Run scripts/google_oauth_setup.py once "
            "to authorize it (see README)."
        )
    creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token_path.write_text(creds.to_json())
    return creds
