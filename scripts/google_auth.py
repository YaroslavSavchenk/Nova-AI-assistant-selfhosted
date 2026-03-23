"""
Google Calendar service account connection test.

Verifies that the service account credentials in data/service.account.json
are valid and can read the configured calendar. Run this once after setup
to confirm everything is working before starting Nova.

    python3 scripts/google_auth.py

No browser flow — service account auth requires no user interaction.
"""

import sys
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent.parent))

_SERVICE_ACCOUNT_FILE = Path("data/service.account.json")
_SCOPES = ["https://www.googleapis.com/auth/calendar"]


def _load_calendar_id() -> str:
    """Read calendar_id from config.yaml, fall back to a prompt."""
    try:
        import yaml
        config = yaml.safe_load(Path("config.yaml").read_text())
        cal_id = config.get("modules", {}).get("calendar_id", "")
        if cal_id:
            return cal_id
    except Exception:
        pass
    return input("Enter your Google Calendar ID (your Gmail address): ").strip()


def main() -> None:
    if not _SERVICE_ACCOUNT_FILE.exists():
        print(f"ERROR: {_SERVICE_ACCOUNT_FILE} not found.")
        print("Place your service account JSON key at: data/service.account.json")
        print("Create one in Google Cloud Console → IAM & Admin → Service Accounts → Keys.")
        sys.exit(1)

    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
    except ImportError:
        print("ERROR: Google packages not installed.")
        print("Run: pip install google-auth google-api-python-client --break-system-packages")
        sys.exit(1)

    calendar_id = _load_calendar_id()
    if not calendar_id:
        print("ERROR: No calendar ID provided.")
        sys.exit(1)

    print(f"Loading service account credentials from {_SERVICE_ACCOUNT_FILE}...")
    creds = service_account.Credentials.from_service_account_file(
        str(_SERVICE_ACCOUNT_FILE),
        scopes=_SCOPES,
    )

    print("Connecting to Google Calendar API...")
    service = build("calendar", "v3", credentials=creds)

    print(f"Fetching upcoming events from: {calendar_id}\n")
    now = datetime.now(timezone.utc).isoformat()
    result = service.events().list(
        calendarId=calendar_id,
        timeMin=now,
        maxResults=5,
        singleEvents=True,
        orderBy="startTime",
    ).execute()

    events = result.get("items", [])
    if not events:
        print("No upcoming events found.")
        print()
        print("If you expected events, make sure the calendar is shared with the service account.")
        print("Find the service account email in data/service.account.json under 'client_email',")
        print("then share your Google Calendar with that address (Make changes to events).")
    else:
        print(f"Found {len(events)} upcoming event(s):\n")
        for event in events:
            start = event["start"].get("dateTime", event["start"].get("date"))
            print(f"  - {event.get('summary', '(no title)')} @ {start}")

    print("\nService account connection successful!")


if __name__ == "__main__":
    main()
