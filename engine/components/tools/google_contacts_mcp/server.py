"""
FastMCP server exposing read-only Google Contacts tools over stdio.

Run:
    uv run python -m engine.components.tools.google_contacts_mcp.server

Expects GOOGLE_CONTACTS_ACCESS_TOKEN in the environment.
"""

import warnings
from typing import Annotated, Any

from pydantic import Field

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    from fastmcp import FastMCP

from engine.components.tools.google_contacts_mcp.client import (
    DEFAULT_OTHER_CONTACTS_READ_MASK,
    DEFAULT_OTHER_CONTACTS_SEARCH_READ_MASK,
    DEFAULT_PERSON_FIELDS,
    GoogleContactsClient,
)
from engine.components.types import ToolDescription
from engine.llm_services.utils import resolve_schema_refs

mcp = FastMCP("google-contacts")
_client: GoogleContactsClient


@mcp.tool(
    name="contacts_list_contacts",
    description=(
        "List contacts and Other contacts from the authenticated Google account. Returns people resources "
        "with names, email addresses, phone numbers, organizations, photos, and metadata by default. "
        "Always returns nextSyncToken / nextOtherContactsSyncToken on the last page; pass sync_token / "
        "other_contacts_sync_token to fetch only changes (including deletions) since that token."
    ),
)
async def contacts_list_contacts(
    max_results: Annotated[int, Field(ge=1, le=1000)] = 100,
    person_fields: str = DEFAULT_PERSON_FIELDS,
    page_token: str | None = None,
    include_other_contacts: bool = True,
    other_contacts_page_token: str | None = None,
    other_contacts_read_mask: str = DEFAULT_OTHER_CONTACTS_READ_MASK,
    sync_token: str | None = None,
    other_contacts_sync_token: str | None = None,
) -> dict[str, Any]:
    return await _client.list_contacts(
        max_results=max_results,
        person_fields=person_fields,
        page_token=page_token,
        include_other_contacts=include_other_contacts,
        other_contacts_page_token=other_contacts_page_token,
        other_contacts_read_mask=other_contacts_read_mask,
        sync_token=sync_token or None,
        other_contacts_sync_token=other_contacts_sync_token or None,
    )


@mcp.tool(
    name="contacts_search_contacts",
    description=(
        "Search contacts and Other contacts of the authenticated Google account by name, email address, or "
        "phone number prefix. Returns at most page_size matches per source (Google caps search at 30)."
    ),
)
async def contacts_search_contacts(
    query: str,
    page_size: Annotated[int, Field(ge=1, le=30)] = 10,
    person_fields: str = DEFAULT_PERSON_FIELDS,
    other_contacts_read_mask: str = DEFAULT_OTHER_CONTACTS_SEARCH_READ_MASK,
) -> dict[str, Any]:
    return await _client.search_contacts(
        query=query,
        page_size=page_size,
        person_fields=person_fields,
        other_contacts_read_mask=other_contacts_read_mask,
    )


@mcp.tool(
    name="contacts_get_contact",
    description="Get a single Google contact by its people resource name, for example 'people/c123'.",
)
async def contacts_get_contact(
    resource_name: str,
    person_fields: str = DEFAULT_PERSON_FIELDS,
) -> dict[str, Any]:
    return await _client.get_contact(resource_name=resource_name, person_fields=person_fields)


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

    token = os.environ.get("GOOGLE_CONTACTS_ACCESS_TOKEN")
    if not token:
        raise RuntimeError("GOOGLE_CONTACTS_ACCESS_TOKEN environment variable is required")

    _client = GoogleContactsClient(token)
    mcp.run(show_banner=False)
