"""
Thin async client for the Google Calendar API.

Uses the Google API Python client under the hood, but wraps calls in
asyncio.to_thread so the FastMCP server stays non-blocking.
"""

import asyncio
from typing import Any

from engine.integrations.utils import get_google_calendar_service


class GoogleCalendarClient:
    def __init__(self, access_token: str) -> None:
        if not access_token:
            raise ValueError("access_token is required")
        self._service = get_google_calendar_service(access_token)

    async def list_calendars(self) -> list[dict[str, Any]]:
        def _call():
            result = self._service.calendarList().list().execute()
            return result.get("items", [])

        return await asyncio.to_thread(_call)

    async def list_events(
        self,
        calendar_id: str = "primary",
        time_min: str | None = None,
        time_max: str | None = None,
        max_results: int = 50,
        query: str | None = None,
    ) -> list[dict[str, Any]]:
        def _call():
            kwargs: dict[str, Any] = {
                "calendarId": calendar_id,
                "maxResults": max_results,
                "singleEvents": True,
                "orderBy": "startTime",
            }
            if time_min:
                kwargs["timeMin"] = time_min
            if time_max:
                kwargs["timeMax"] = time_max
            if query:
                kwargs["q"] = query
            result = self._service.events().list(**kwargs).execute()
            return result.get("items", [])

        return await asyncio.to_thread(_call)

    async def get_event(self, event_id: str, calendar_id: str = "primary") -> dict[str, Any]:
        def _call():
            return self._service.events().get(calendarId=calendar_id, eventId=event_id).execute()

        return await asyncio.to_thread(_call)

    async def create_event(self, event_body: dict[str, Any], calendar_id: str = "primary") -> dict[str, Any]:
        def _call():
            return (
                self._service.events()
                .insert(calendarId=calendar_id, body=event_body, conferenceDataVersion=1)
                .execute()
            )

        return await asyncio.to_thread(_call)

    async def update_event(
        self, event_id: str, event_body: dict[str, Any], calendar_id: str = "primary"
    ) -> dict[str, Any]:
        def _call():
            return (
                self._service.events()
                .patch(calendarId=calendar_id, eventId=event_id, body=event_body, conferenceDataVersion=1)
                .execute()
            )

        return await asyncio.to_thread(_call)

    async def delete_event(self, event_id: str, calendar_id: str = "primary") -> dict[str, Any]:
        def _call():
            self._service.events().delete(calendarId=calendar_id, eventId=event_id).execute()
            return {"status": "deleted", "eventId": event_id}

        return await asyncio.to_thread(_call)
