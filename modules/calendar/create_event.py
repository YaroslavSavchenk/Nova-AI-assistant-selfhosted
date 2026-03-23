"""Calendar create event tool."""

import asyncio
import logging

from modules.base import NovaModule
from modules.calendar._client import build_service

logger = logging.getLogger(__name__)


class CalendarCreateEventModule(NovaModule):
    name: str = "calendar_create_event"
    description: str = (
        "Create a new Google Calendar event. "
        "IMPORTANT: Before calling this tool you MUST present the event details "
        "(title, date, start time, end time) to the user and ask for confirmation. "
        "Only call this tool after the user explicitly confirms. "
        "You MUST call this tool to create the event — saying 'Done' without calling it does nothing. "
        "Provide start and end in ISO 8601 format (e.g. '2026-03-25T17:00:00'). "
        "Default event duration is 1 hour if the user does not specify an end time."
    )
    parameters: dict = {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "Event title / summary",
            },
            "start": {
                "type": "string",
                "description": "Start datetime in ISO 8601 format, e.g. '2026-03-25T17:00:00'",
            },
            "end": {
                "type": "string",
                "description": "End datetime in ISO 8601 format, e.g. '2026-03-25T18:00:00'",
            },
            "description": {
                "type": "string",
                "description": "Optional event description or notes",
            },
        },
        "required": ["title", "start", "end"],
    }

    def __init__(self, calendar_id: str, timezone: str) -> None:
        self.calendar_id = calendar_id
        self.timezone = timezone

    async def run(self, **kwargs) -> str:
        try:
            title: str = kwargs["title"]
            start: str = kwargs["start"]
            end: str = kwargs["end"]
            description: str = kwargs.get("description", "")
            return await asyncio.to_thread(self._create_event, title, start, end, description)
        except KeyError as exc:
            return (
                f"Calendar error: missing required field {exc}. "
                "Please provide title, start, and end in ISO 8601 format (e.g. '2026-03-25T17:00:00')."
            )
        except Exception as exc:
            logger.exception("calendar_create_event failed")
            return f"Calendar error: {exc}"

    def _create_event(self, title: str, start: str, end: str, description: str) -> str:
        service = build_service()
        event_body = {
            "summary": title,
            "start": {"dateTime": start, "timeZone": self.timezone},
            "end": {"dateTime": end, "timeZone": self.timezone},
        }
        if description:
            event_body["description"] = description

        created = service.events().insert(
            calendarId=self.calendar_id,
            body=event_body,
        ).execute()

        event_id = created["id"]

        # Verify the event actually exists by fetching it back
        verified = service.events().get(
            calendarId=self.calendar_id,
            eventId=event_id,
        ).execute()

        if verified.get("id") != event_id:
            return "WARNING: Event may not have been saved correctly. Please check your calendar."

        return f"Event created and verified: '{title}' from {start} to {end}."
