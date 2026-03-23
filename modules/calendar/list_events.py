"""Calendar list events tool."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from modules.base import NovaModule
from modules.calendar._client import build_service

logger = logging.getLogger(__name__)


class CalendarListEventsModule(NovaModule):
    name: str = "calendar_list_events"
    description: str = (
        "List upcoming Google Calendar events. "
        "Optionally specify how many days ahead to look (default: 7). "
        "Returns event titles, times, and internal IDs. "
        "Never show event IDs to the user — they are for internal tool use only."
    )
    parameters: dict = {
        "type": "object",
        "properties": {
            "days_ahead": {
                "type": "integer",
                "description": "How many days ahead to fetch events (default: 7)",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of events to return (default: 10)",
            },
        },
        "required": [],
    }

    def __init__(self, calendar_id: str, timezone: str) -> None:
        self.calendar_id = calendar_id
        self.timezone = timezone

    async def run(self, **kwargs) -> str:
        days_ahead: int = int(kwargs.get("days_ahead", 7))
        max_results: int = int(kwargs.get("max_results", 10))
        try:
            return await asyncio.to_thread(self._fetch_events, days_ahead, max_results)
        except Exception as exc:
            logger.exception("calendar_list_events failed")
            return f"Calendar error: {exc}"

    def _fetch_events(self, days_ahead: int, max_results: int) -> str:
        service = build_service()
        now = datetime.now(timezone.utc)
        time_max = (now + timedelta(days=days_ahead)).isoformat()

        events_result = service.events().list(
            calendarId=self.calendar_id,
            timeMin=now.isoformat(),
            timeMax=time_max,
            maxResults=max_results,
            singleEvents=True,
            orderBy="startTime",
        ).execute()

        events = events_result.get("items", [])
        if not events:
            return f"No events found in the next {days_ahead} day(s)."

        lines = [f"Upcoming events (next {days_ahead} day(s)):\n"]
        for event in events:
            start = event["start"].get("dateTime", event["start"].get("date"))
            summary = event.get("summary", "(no title)")
            event_id = event["id"]
            lines.append(f"- {summary} | {start} | id:{event_id}")  # ID is for tool use only, do not show to user

        return "\n".join(lines)
