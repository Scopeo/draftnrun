"""
FastMCP server exposing Notion tools over stdio.

Run:
    uv run python -m engine.components.tools.notion_mcp.server

Expects NOTION_ACCESS_TOKEN in the environment.
"""

import warnings
from typing import Any, Optional

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    from fastmcp import FastMCP

from engine.components.tools.notion_mcp.client import NotionClient
from engine.components.types import ToolDescription
from engine.llm_services.utils import resolve_schema_refs

mcp = FastMCP("notion")
_client: NotionClient


# ---------------------------------------------------------------------------
# Tier 1 — CRUD Primitives
# ---------------------------------------------------------------------------


@mcp.tool(
    name="search",
    description=(
        "Search Notion by title across all pages and databases the integration can access. "
        "Returns matching pages and databases sorted by relevance."
    ),
)
async def search(
    query: Optional[str] = None,
    filter_object_type: Optional[str] = None,
    page_size: int = 20,
    start_cursor: Optional[str] = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {}
    if query:
        body["query"] = query
    if filter_object_type:
        body["filter"] = {"value": filter_object_type, "property": "object"}
    if page_size:
        body["page_size"] = page_size
    if start_cursor:
        body["start_cursor"] = start_cursor
    return await _client.request("post", "/v1/search", json=body)


@mcp.tool(
    name="get_self",
    description="Get the bot user associated with the current integration token. Useful for verifying connectivity.",
)
async def get_self() -> dict[str, Any]:
    return await _client.request("get", "/v1/users/me")


@mcp.tool(
    name="get_database",
    description="Retrieve a database schema by ID. Returns the database properties (columns) and metadata.",
)
async def get_database(database_id: str) -> dict[str, Any]:
    return await _client.request("get", f"/v1/databases/{database_id}")


@mcp.tool(
    name="create_database",
    description=(
        "Create a new database as a child of a parent page. "
        "Properties define the database schema (columns). "
        "Each property key is the column name, value is the type config "
        '(e.g. {"Email": {"email": {}}, "Name": {"title": {}}}). '
        "Every database must have exactly one title property."
    ),
)
async def create_database(
    parent_page_id: str,
    title: str,
    properties: dict[str, Any],
    is_inline: bool = False,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "parent": {"type": "page_id", "page_id": parent_page_id},
        "title": [{"type": "text", "text": {"content": title}}],
        "properties": properties,
        "is_inline": is_inline,
    }
    return await _client.request("post", "/v1/databases", json=body)


@mcp.tool(
    name="update_database",
    description=(
        "Update a database's title or properties (add/rename/remove columns). "
        "To add a new property, include it in properties with its type config. "
        "To remove a property, set its value to null."
    ),
)
async def update_database(
    database_id: str,
    title: Optional[str] = None,
    properties: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {}
    if title is not None:
        body["title"] = [{"type": "text", "text": {"content": title}}]
    if properties is not None:
        body["properties"] = properties
    return await _client.request("patch", f"/v1/databases/{database_id}", json=body)


@mcp.tool(
    name="query_database",
    description=(
        "Query a Notion database with optional filter and sorts. "
        "Filter uses Notion's compound filter syntax: "
        '{"and": [{"property": "Email", "email": {"equals": "foo@bar.com"}}]}. '
        "Returns matching pages (rows)."
    ),
)
async def query_database(
    database_id: str,
    filter: Optional[dict[str, Any]] = None,
    sorts: Optional[list[dict[str, Any]]] = None,
    page_size: int = 100,
    start_cursor: Optional[str] = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {"page_size": page_size}
    if filter:
        body["filter"] = filter
    if sorts:
        body["sorts"] = sorts
    if start_cursor:
        body["start_cursor"] = start_cursor
    return await _client.request("post", f"/v1/databases/{database_id}/query", json=body)


@mcp.tool(
    name="create_page",
    description=(
        "Create a page in a database or as a child of another page. "
        "For database rows, parent is {database_id: ...} and properties are column values. "
        "For sub-pages, parent is {page_id: ...} and properties must include a title. "
        "Optionally include children blocks for the page body."
    ),
)
async def create_page(
    parent: dict[str, Any],
    properties: dict[str, Any],
    children: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {"parent": parent, "properties": properties}
    if children:
        body["children"] = children
    return await _client.request("post", "/v1/pages", json=body)


@mcp.tool(
    name="update_page",
    description="Update page properties (database row columns). Does not update the page body blocks.",
)
async def update_page(
    page_id: str,
    properties: dict[str, Any],
) -> dict[str, Any]:
    return await _client.request("patch", f"/v1/pages/{page_id}", json={"properties": properties})


@mcp.tool(
    name="get_page",
    description="Retrieve a page by ID, including its properties.",
)
async def get_page(page_id: str) -> dict[str, Any]:
    return await _client.request("get", f"/v1/pages/{page_id}")


@mcp.tool(
    name="append_blocks",
    description=(
        "Append child blocks to a page or block. "
        "Each block must include a type and the matching type key with content. "
        'Example: {"type": "paragraph", "paragraph": {"rich_text": [{"type": "text", "text": {"content": "Hello"}}]}}'
    ),
)
async def append_blocks(
    block_id: str,
    children: list[dict[str, Any]],
) -> dict[str, Any]:
    return await _client.request("patch", f"/v1/blocks/{block_id}/children", json={"children": children})


@mcp.tool(
    name="get_block_children",
    description="List all child blocks of a page or block. Supports pagination.",
)
async def get_block_children(
    block_id: str,
    page_size: int = 100,
    start_cursor: Optional[str] = None,
) -> dict[str, Any]:
    params: dict[str, Any] = {"page_size": page_size}
    if start_cursor:
        params["start_cursor"] = start_cursor
    return await _client.request("get", f"/v1/blocks/{block_id}/children", params=params)


@mcp.tool(
    name="delete_block",
    description="Delete (archive) a block by ID. Also works for pages.",
)
async def delete_block(block_id: str) -> dict[str, Any]:
    return await _client.request("delete", f"/v1/blocks/{block_id}")


# ---------------------------------------------------------------------------
# Tier 2 — Smart Upserts
# ---------------------------------------------------------------------------


@mcp.tool(
    name="upsert_page_by_property",
    description=(
        "Query a database for a page matching a unique property value, "
        "then create or update accordingly. Returns {page_id, operation} "
        'where operation is "created", "updated", or "noop". '
        "For updates, only the provided properties are changed. "
        "Use this for deterministic contact/interaction sync."
    ),
)
async def upsert_page_by_property(
    database_id: str,
    match_property: str,
    match_property_type: str,
    match_value: str,
    properties: dict[str, Any],
) -> dict[str, Any]:
    filter_condition = {match_property_type: {"equals": match_value}}
    query_filter = {"property": match_property, **filter_condition}

    result = await _client.request(
        "post",
        f"/v1/databases/{database_id}/query",
        json={"filter": query_filter, "page_size": 1},
    )

    existing_pages = result.get("results", [])

    if existing_pages:
        page = existing_pages[0]
        page_id = page["id"]
        updated = await _client.request(
            "patch",
            f"/v1/pages/{page_id}",
            json={"properties": properties},
        )
        return {"page_id": page_id, "operation": "updated", "page": updated}

    create_body: dict[str, Any] = {
        "parent": {"database_id": database_id},
        "properties": properties,
    }
    created = await _client.request("post", "/v1/pages", json=create_body)
    return {"page_id": created["id"], "operation": "created", "page": created}


@mcp.tool(
    name="replace_page_blocks",
    description=(
        "Replace all blocks in a page body with new content. "
        "Deletes existing child blocks, then appends the new blocks. "
        "Useful for syncing notes/transcription without appending duplicates."
    ),
)
async def replace_page_blocks(
    page_id: str,
    new_blocks: list[dict[str, Any]],
) -> dict[str, Any]:
    deleted_ids: list[str] = []
    start_cursor: str | None = None
    while True:
        params: dict[str, Any] = {"page_size": 100}
        if start_cursor:
            params["start_cursor"] = start_cursor
        children_resp = await _client.request("get", f"/v1/blocks/{page_id}/children", params=params)
        for block in children_resp.get("results", []):
            block_id = block["id"]
            await _client.request("delete", f"/v1/blocks/{block_id}")
            deleted_ids.append(block_id)
        if not children_resp.get("has_more"):
            break
        start_cursor = children_resp.get("next_cursor")

    appended: dict[str, Any] = {}
    if new_blocks:
        appended = await _client.request(
            "patch",
            f"/v1/blocks/{page_id}/children",
            json={"children": new_blocks},
        )

    return {
        "page_id": page_id,
        "deleted_block_count": len(deleted_ids),
        "appended_block_count": len(new_blocks),
        "appended": appended,
    }


# ---------------------------------------------------------------------------
# Tool description helper (used by the tool wrapper at import time)
# ---------------------------------------------------------------------------


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

    token = os.environ.get("NOTION_ACCESS_TOKEN")
    if not token:
        raise RuntimeError("NOTION_ACCESS_TOKEN environment variable is required")

    _client = NotionClient(token)
    mcp.run(show_banner=False)
