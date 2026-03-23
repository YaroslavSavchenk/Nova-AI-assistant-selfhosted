"""Shared Google Calendar API client for the calendar package."""

from pathlib import Path

_SERVICE_ACCOUNT_FILE = Path("data/service.account.json")
_SCOPES = ["https://www.googleapis.com/auth/calendar"]


def build_service():
    """Build and return a Google Calendar API service client."""
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    creds = service_account.Credentials.from_service_account_file(
        str(_SERVICE_ACCOUNT_FILE),
        scopes=_SCOPES,
    )
    return build("calendar", "v3", credentials=creds)
