"""Run this ONCE, locally (not on the server), to authorize the bot's access to
your Google Sheets and Calendar (read-only) with your own Google login — one
authorization covers both, so there's no service-account key file involved
(Google blocks creating those by default on many accounts/organizations).

Usage:
    python scripts/google_oauth_setup.py

It opens a browser for you to sign in and approve access, then writes the
resulting token to GOOGLE_TOKEN_FILE (see .env). Copy that token file to your
server/deployment afterwards — see README for details.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from google_auth_oauthlib.flow import InstalledAppFlow  # noqa: E402

from app.config import settings  # noqa: E402
from app.services.google_oauth import SCOPES  # noqa: E402


def main() -> None:
    client_file = Path(settings.google_oauth_client_file)
    if not client_file.exists():
        print(f"ERROR: OAuth client file not found at {client_file}.")
        print("Create one in Google Cloud Console (see README 'Google Cloud project setup') and save it there.")
        raise SystemExit(1)

    flow = InstalledAppFlow.from_client_secrets_file(str(client_file), SCOPES)
    creds = flow.run_local_server(port=0)

    token_file = Path(settings.google_token_file)
    token_file.parent.mkdir(parents=True, exist_ok=True)
    token_file.write_text(creds.to_json())

    print(f"\nDone! Token saved to {token_file}.")
    print("Copy this file to your deployment's secrets/ directory (keep it private — it's a live credential).")
    print("This one file now covers both Google Sheets and Google Calendar access.")


if __name__ == "__main__":
    main()
