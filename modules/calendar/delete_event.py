"""Calendar delete event tool."""

import asyncio
import logging

from modules.base import NovaModule
from modules.calendar._client import build_service

logger = logging.getLogger(__name__)


class CalendarDeleteEventModule(NovaModule):
    name: str = "calendar_delete_event"
    description: str = (
        "Delete a Google Calendar event by its ID. "
        "IMPORTANT: Before calling this tool you MUST tell the user which event "
        "you are about to delete and ask for confirmation. "
        "Only call this tool after the user explicitly confirms. "
        "Use calendar_list_events first to find the event ID."
    )
    parameters: dict = {
        "type": "object",
        "properties": {
            "event_id": {
                "type": "string",
                "description": "The Google Calendar event ID to delete",
            },
        },
        "required": ["event_id"],
    }

    def __init__(self, calendar_id: str, timezone: str) -> None:
        self.calendar_id = calendar_id
        self.timezone = timezone

    async def run(self, **kwargs) -> str:
        try:
            event_id: str = kwargs["event_id"]
            await asyncio.to_thread(self._delete_event, event_id)
            return f"Event deleted successfully."
        except KeyError as exc:
            return (
                f"Calendar error: missing required field {exc}. "
                "Use calendar_list_events first to get the event ID."
            )
        except Exception as exc:
            logger.exception("calendar_delete_event failed")
            return f"Calendar error: {exc}"

    def _delete_event(self, event_id: str) -> None:
        service = build_service()
        service.events().delete(
            calendarId=self.calendar_id,
            eventId=event_id,
        ).execute()
