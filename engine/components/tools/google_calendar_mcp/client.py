"""
Thin async client for the Google Calendar API.

Uses the Google API Python client under the hood, but wraps calls in
asyncio.to_thread so the FastMCP server stays non-blocking.

This module is imported by the MCP stdio subprocess (server.py), so it must NOT
import anything from ada_backend/ — the subprocess runs with a minimal
environment and ada_backend.database.models would crash on missing FERNET_KEY.
"""

import asyncio
from typing import Any

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build


class GoogleCalendarClient:
    def __init__(self, access_token: str) -> None:
        if not access_token:
            raise ValueError("access_token is required")
        creds = Credentials(token=access_token)
        self._service = build("calendar", "v3", credentials=creds)
        self._user_email: str | None = None

    async def get_user_email(self) -> str:
        if self._user_email is None:
            def _call():
                cal = self._service.calendarList().get(calendarId="primary").execute()
                return cal["id"]

            self._user_email = await asyncio.to_thread(_call)
        return self._user_email

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
                .insert(calendarId=calendar_id, body=event_body, conferenceDataVersion=1, sendUpdates="all")
                .execute()
            )

        return await asyncio.to_thread(_call)

    async def update_event(
        self, event_id: str, event_body: dict[str, Any], calendar_id: str = "primary"
    ) -> dict[str, Any]:
        def _call():
            return (
                self._service.events()
                .patch(
                    calendarId=calendar_id,
                    eventId=event_id,
                    body=event_body,
                    conferenceDataVersion=1,
                    sendUpdates="all",
                )
                .execute()
            )

        return await asyncio.to_thread(_call)

    async def delete_event(self, event_id: str, calendar_id: str = "primary") -> dict[str, Any]:
        def _call():
            self._service.events().delete(calendarId=calendar_id, eventId=event_id, sendUpdates="all").execute()
            return {"status": "deleted", "eventId": event_id}

        return await asyncio.to_thread(_call)
