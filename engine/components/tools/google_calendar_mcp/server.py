"""
FastMCP server exposing Google Calendar tools over stdio.

Run:
    uv run python -m engine.components.tools.google_calendar_mcp.server

Expects GOOGLE_CALENDAR_ACCESS_TOKEN in the environment.
"""

import warnings
from typing import Any, Optional

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    from fastmcp import FastMCP

from engine.components.tools.google_calendar_mcp.client import GoogleCalendarClient
from engine.components.tools.google_calendar_mcp.schema import EventBody
from engine.components.types import ToolDescription
from engine.llm_services.utils import resolve_schema_refs

mcp = FastMCP("google-calendar")
_client: GoogleCalendarClient


@mcp.tool(
    name="calendar_list_calendars",
    description="List all calendars accessible to the authenticated user.",
)
async def calendar_list_calendars() -> list[dict[str, Any]]:
    return await _client.list_calendars()


@mcp.tool(
    name="calendar_list_events",
    description=(
        "List events from a calendar. Returns events ordered by start time. "
        "Use timeMin/timeMax (RFC3339) to filter by date range."
    ),
)
async def calendar_list_events(
    calendar_id: str = "primary",
    time_min: Optional[str] = None,
    time_max: Optional[str] = None,
    max_results: int = 50,
    query: Optional[str] = None,
) -> list[dict[str, Any]]:
    return await _client.list_events(
        calendar_id=calendar_id,
        time_min=time_min,
        time_max=time_max,
        max_results=max_results,
        query=query,
    )


@mcp.tool(
    name="calendar_get_event",
    description="Get a single event by its ID.",
)
async def calendar_get_event(
    event_id: str,
    calendar_id: str = "primary",
) -> dict[str, Any]:
    return await _client.get_event(event_id=event_id, calendar_id=calendar_id)


@mcp.tool(
    name="calendar_get_my_email",
    description="Return the email address of the authenticated calendar owner.",
)
async def calendar_get_my_email() -> dict[str, str]:
    email = await _client.get_user_email()
    return {"email": email}


@mcp.tool(
    name="calendar_create_event",
    description=(
        "Create a new event on a Google Calendar. "
        "Provide start and end as RFC3339 datetime strings with timezone offset "
        "(e.g. '2026-03-20T10:00:00+01:00') or as date strings for all-day events. "
        "To add a Google Meet link, include conferenceData with a createRequest. "
        "When adding attendees, don't forget to also add the calendar owner if they "
        "should participate in the meeting, otherwise they won't appear as an attendee. "
        "Use calendar_get_my_email to get the owner's email if needed."
    ),
)
async def calendar_create_event(
    event: EventBody,
    calendar_id: str = "primary",
) -> dict[str, Any]:
    body = event.model_dump(exclude_none=True)
    return await _client.create_event(event_body=body, calendar_id=calendar_id)


@mcp.tool(
    name="calendar_update_event",
    description=(
        "Update an existing event. Only provided fields are changed; "
        "omitted fields keep their current values."
    ),
)
async def calendar_update_event(
    event_id: str,
    event: EventBody,
    calendar_id: str = "primary",
) -> dict[str, Any]:
    body = event.model_dump(exclude_none=True)
    return await _client.update_event(event_id=event_id, event_body=body, calendar_id=calendar_id)


@mcp.tool(
    name="calendar_delete_event",
    description="Delete an event by its ID. This action is irreversible.",
)
async def calendar_delete_event(
    event_id: str,
    calendar_id: str = "primary",
) -> dict[str, Any]:
    return await _client.delete_event(event_id=event_id, calendar_id=calendar_id)


async def get_tool_descriptions(allowed: set[str]) -> list[ToolDescription]:
    result = []
    for tool in await mcp.list_tools():
        if tool.name not in allowed:
            continue
        params = tool.parameters or {}
        resolved_params = resolve_schema_refs(params) if isinstance(params, dict) else params
        result.append(
            ToolDescription(
                name=tool.name,
                description=tool.description or "",
                tool_properties=resolved_params.get("properties", {}),
                required_tool_properties=resolved_params.get("required", []),
            )
        )
    return result


if __name__ == "__main__":
    import os

    token = os.environ.get("GOOGLE_CALENDAR_ACCESS_TOKEN")
    if not token:
        raise RuntimeError("GOOGLE_CALENDAR_ACCESS_TOKEN environment variable is required")

    _client = GoogleCalendarClient(token)
    mcp.run(show_banner=False)
