"""
Thin async client for the Microsoft Graph Calendar API.

Uses httpx for all HTTP calls wrapped in asyncio-friendly patterns.

This module is imported by the MCP stdio subprocess (server.py), so it must NOT
import anything from ada_backend/ — the subprocess runs with a minimal
environment and ada_backend.database.models would crash on missing FERNET_KEY.
"""

import logging
from typing import Any, Optional

import httpx

GRAPH_API_BASE = "https://graph.microsoft.com/v1.0"
LOGGER = logging.getLogger(__name__)


class OutlookCalendarClient:
    def __init__(self, access_token: str) -> None:
        if not access_token:
            raise ValueError("access_token is required")
        self._access_token = access_token
        self._user_email: str | None = None
        self._default_calendar_id: str | None = None

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
        }

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        timeout: float = 30.0,
    ) -> httpx.Response:
        url = f"{GRAPH_API_BASE}{path}"
        LOGGER.info("HTTP %s %s params=%s", method, url, params)
        async with httpx.AsyncClient() as client:
            response = await client.request(
                method,
                url,
                headers=self._headers(),
                params=params,
                json=json_body,
                timeout=timeout,
            )
        LOGGER.info("HTTP %s %s -> %d (%d bytes)", method, url, response.status_code, len(response.content))
        response.raise_for_status()
        return response

    async def get_user_email(self) -> str:
        if self._user_email is None:
            resp = await self._request("GET", "/me", params={"$select": "mail,userPrincipalName"})
            data = resp.json()
            self._user_email = data.get("mail") or data.get("userPrincipalName")
            if not self._user_email:
                raise RuntimeError("Could not determine Outlook user email address")
        return self._user_email

    async def list_calendars(self) -> list[dict[str, Any]]:
        resp = await self._request("GET", "/me/calendars", params={"$top": "100"})
        return resp.json().get("value", [])

    async def _resolve_calendar_id(self, calendar_id: str) -> str:
        if calendar_id != "primary":
            return calendar_id
        if self._default_calendar_id is None:
            LOGGER.info("Resolving default calendar ID via /me/calendar")
            resp = await self._request("GET", "/me/calendar", params={"$select": "id,name"})
            data = resp.json()
            self._default_calendar_id = data["id"]
            LOGGER.info("Default calendar: id=%s name=%s", data["id"], data.get("name"))
        return self._default_calendar_id

    async def list_events(
        self,
        calendar_id: str = "primary",
        time_min: Optional[str] = None,
        time_max: Optional[str] = None,
        max_results: int = 50,
        query: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        resolved_id = await self._resolve_calendar_id(calendar_id)
        LOGGER.info("list_events: resolved calendar_id=%s -> %s", calendar_id, resolved_id)
        prefix = f"/me/calendars/{resolved_id}"
        if time_min and time_max:
            path = f"{prefix}/calendarView"
            params: dict[str, Any] = {
                "startDateTime": time_min,
                "endDateTime": time_max,
                "$top": str(max_results),
                "$orderby": "start/dateTime",
            }
        else:
            path = f"{prefix}/events"
            params = {
                "$top": str(max_results),
                "$orderby": "start/dateTime",
            }
            filters: list[str] = []
            if time_min:
                filters.append(f"start/dateTime ge '{time_min}'")
            if time_max:
                filters.append(f"start/dateTime le '{time_max}'")
            if filters:
                params["$filter"] = " and ".join(filters)

        if query:
            params["$search"] = f'"{query}"'

        resp = await self._request("GET", path, params=params)
        return resp.json().get("value", [])

    async def get_event(self, event_id: str) -> dict[str, Any]:
        resp = await self._request("GET", f"/me/events/{event_id}")
        return resp.json()

    async def create_event(
        self, event_body: dict[str, Any], calendar_id: str = "primary"
    ) -> dict[str, Any]:
        resolved_id = await self._resolve_calendar_id(calendar_id)
        LOGGER.info("create_event: resolved calendar_id=%s -> %s", calendar_id, resolved_id)
        resp = await self._request("POST", f"/me/calendars/{resolved_id}/events", json_body=event_body)
        return resp.json()

    async def update_event(self, event_id: str, event_body: dict[str, Any]) -> dict[str, Any]:
        resp = await self._request("PATCH", f"/me/events/{event_id}", json_body=event_body)
        return resp.json()

    async def delete_event(self, event_id: str) -> dict[str, Any]:
        await self._request("DELETE", f"/me/events/{event_id}")
        return {"status": "deleted", "eventId": event_id}
