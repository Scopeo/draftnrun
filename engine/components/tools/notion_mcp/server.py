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


def _property_by_name(properties: dict[str, Any], property_name: str) -> dict[str, Any]:
    property_config = properties.get(property_name)
    if not property_config:
        raise RuntimeError(f"Data source does not have property {property_name!r}")
    return property_config


def _table_property_config(property_config: dict[str, Any], visible: bool = True, width: int = 180) -> dict[str, Any]:
    return {"property_id": property_config["id"], "visible": visible, "width": width}


def _group_by_type(property_type: str) -> str:
    if property_type == "rich_text":
        return "text"
    if property_type == "people":
        return "person"
    return property_type


def _group_by_config(property_config: dict[str, Any], group_by: Optional[str]) -> dict[str, Any]:
    property_type = _group_by_type(property_config["type"])
    config: dict[str, Any] = {
        "type": property_type,
        "property_id": property_config["id"],
        "sort": {"type": "ascending"},
        "hide_empty_groups": True,
    }
    if group_by:
        config["group_by"] = group_by
    elif property_type in {"title", "rich_text", "url", "email", "phone_number"}:
        config["group_by"] = "exact"
    elif property_type == "status":
        config["group_by"] = "option"
    elif property_type == "date":
        config["group_by"] = "month"
    return config


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
    description=(
        "Retrieve a database container by ID. In Notion API 2026-03-11, schemas and rows live on data "
        "sources; use get_data_source to retrieve properties."
    ),
)
async def get_database(database_id: str) -> dict[str, Any]:
    return await _client.request("get", f"/v1/databases/{database_id}")


@mcp.tool(
    name="create_database",
    description=(
        "Create a new database as a child of a parent page. "
        "initial_data_source_properties define the first data source schema (columns). "
        "Each property key is the column name, value is the type config "
        '(e.g. {"Email": {"email": {}}, "Name": {"title": {}}}). '
        "Every initial data source must have exactly one title property. "
        "Optionally set an emoji icon at creation time."
    ),
)
async def create_database(
    parent_page_id: str,
    title: str,
    initial_data_source_properties: dict[str, Any],
    is_inline: bool = False,
    icon: Optional[str] = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "parent": {"type": "page_id", "page_id": parent_page_id},
        "title": [{"type": "text", "text": {"content": title}}],
        "initial_data_source": {"properties": initial_data_source_properties},
        "is_inline": is_inline,
    }
    if icon:
        body["icon"] = {"type": "emoji", "emoji": icon}
    return await _client.request("post", "/v1/databases", json=body)


@mcp.tool(
    name="update_database",
    description=(
        "Update database container metadata. In Notion API 2026-03-11, schemas live on data sources; "
        "use update_data_source to add, rename, or remove columns."
    ),
)
async def update_database(
    database_id: str,
    title: str,
) -> dict[str, Any]:
    return await _client.request(
        "patch",
        f"/v1/databases/{database_id}",
        json={"title": [{"type": "text", "text": {"content": title}}]},
    )


@mcp.tool(
    name="get_data_source",
    description="Retrieve a data source by ID, including its properties (columns).",
)
async def get_data_source(data_source_id: str) -> dict[str, Any]:
    return await _client.request("get", f"/v1/data_sources/{data_source_id}")


@mcp.tool(
    name="update_data_source",
    description=(
        "Update a data source's title or properties (add/rename/remove columns). "
        "To add a new property, include it in properties with its type config. "
        "To remove a property, set its value to null."
    ),
)
async def update_data_source(
    data_source_id: str,
    title: Optional[str] = None,
    properties: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {}
    if title is not None:
        body["title"] = [{"type": "text", "text": {"content": title}}]
    if properties is not None:
        body["properties"] = properties
    return await _client.request("patch", f"/v1/data_sources/{data_source_id}", json=body)


@mcp.tool(
    name="query_data_source",
    description=(
        "Query a Notion data source with optional filter and sorts. "
        "Filter uses Notion's compound filter syntax: "
        '{"and": [{"property": "Email", "email": {"equals": "foo@bar.com"}}]}. '
        "Returns matching pages (rows)."
    ),
)
async def query_data_source(
    data_source_id: str,
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
    return await _client.request("post", f"/v1/data_sources/{data_source_id}/query", json=body)


@mcp.tool(
    name="create_page",
    description=(
        "Create a page in a database or as a child of another page. "
        "For data source rows, parent is {type: 'data_source_id', data_source_id: ...} "
        "and properties are column values. "
        "For sub-pages, parent is {page_id: ...} and properties must include a title. "
        "Optionally include children blocks for the page body and an emoji icon."
    ),
)
async def create_page(
    parent: dict[str, Any],
    properties: dict[str, Any],
    children: Optional[list[dict[str, Any]]] = None,
    icon: Optional[str] = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {"parent": parent, "properties": properties}
    if children:
        body["children"] = children
    if icon:
        body["icon"] = {"type": "emoji", "emoji": icon}
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
# Tier 1b — Presentation & Views
# ---------------------------------------------------------------------------


@mcp.tool(
    name="set_icon",
    description=(
        "Set an emoji icon on a page or database. "
        'target_type must be "page" or "database". '
        'emoji is a single Unicode emoji character (e.g. "\U0001f4c7", "\U0001f3e2").'
    ),
)
async def set_icon(
    target_id: str,
    emoji: str,
    target_type: str = "page",
) -> dict[str, Any]:
    icon_payload: dict[str, Any] = {"icon": {"type": "emoji", "emoji": emoji}}
    if target_type == "database":
        return await _client.request("patch", f"/v1/databases/{target_id}", json=icon_payload)
    return await _client.request("patch", f"/v1/pages/{target_id}", json=icon_payload)


@mcp.tool(
    name="list_views",
    description="List all views for a data source. Returns view IDs and types.",
)
async def list_views(data_source_id: str) -> dict[str, Any]:
    return await _client.request("get", "/v1/views", params={"data_source_id": data_source_id})


@mcp.tool(
    name="create_raw_view",
    description=(
        "Create a view on a database/data source pair using raw Notion API payloads. "
        'type can be "table", "board", "gallery", "list", "calendar", or "timeline". '
        "Prefer create_table_view for table views with column visibility, grouping, and sorts. "
        "Use this tool for non-table view types or when you need full control over the configuration payload."
    ),
)
async def create_raw_view(
    database_id: str,
    data_source_id: str,
    type: str = "table",
    name: Optional[str] = None,
    filter: Optional[dict[str, Any]] = None,
    sorts: Optional[list[dict[str, Any]]] = None,
    quick_filters: Optional[list[dict[str, Any]]] = None,
    configuration: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {"database_id": database_id, "data_source_id": data_source_id, "type": type}
    if name:
        body["name"] = name
    if filter:
        body["filter"] = filter
    if sorts:
        body["sorts"] = sorts
    if quick_filters:
        body["quick_filters"] = quick_filters
    if configuration:
        body["configuration"] = configuration
    return await _client.request("post", "/v1/views", json=body)


@mcp.tool(
    name="create_table_view",
    description=(
        "Create a table view with high-level layout options. Resolves property names to Notion property IDs, "
        "sets visible columns, optional grouping, filters, and sorts."
    ),
)
async def create_table_view(
    database_id: str,
    data_source_id: str,
    name: str,
    visible_properties: list[str],
    filter: Optional[dict[str, Any]] = None,
    sorts: Optional[list[dict[str, Any]]] = None,
    group_by_property: Optional[str] = None,
    group_by: Optional[str] = None,
    wrap_cells: bool = False,
    frozen_column_index: int = 1,
    show_vertical_lines: bool = True,
) -> dict[str, Any]:
    data_source = await _client.request("get", f"/v1/data_sources/{data_source_id}")
    properties = data_source.get("properties", {})
    visible_property_names = set(visible_properties)

    configuration: dict[str, Any] = {
        "type": "table",
        "properties": [
            _table_property_config(_property_by_name(properties, property_name))
            for property_name in visible_properties
        ]
        + [
            _table_property_config(property_config, visible=False)
            for property_name, property_config in properties.items()
            if property_name not in visible_property_names
        ],
        "wrap_cells": wrap_cells,
        "frozen_column_index": frozen_column_index,
        "show_vertical_lines": show_vertical_lines,
    }

    if group_by_property:
        property_config = _property_by_name(properties, group_by_property)
        configuration["group_by"] = _group_by_config(property_config, group_by)

    body: dict[str, Any] = {
        "database_id": database_id,
        "data_source_id": data_source_id,
        "type": "table",
        "name": name,
        "configuration": configuration,
    }
    if filter:
        body["filter"] = filter
    if sorts:
        body["sorts"] = sorts
    return await _client.request("post", "/v1/views", json=body)


# ---------------------------------------------------------------------------
# Tier 2 — Smart Upserts
# ---------------------------------------------------------------------------


async def _replace_blocks(
    page_id: str,
    new_blocks: list[dict[str, Any]],
    preserve_block_types: Optional[list[str]] = None,
) -> dict[str, Any]:
    preserved_types = set(["child_database", "child_page"] if preserve_block_types is None else preserve_block_types)
    deleted_ids: list[str] = []
    preserved_ids: list[str] = []
    start_cursor: str | None = None
    while True:
        params: dict[str, Any] = {"page_size": 100}
        if start_cursor:
            params["start_cursor"] = start_cursor
        children_resp = await _client.request("get", f"/v1/blocks/{page_id}/children", params=params)
        for block in children_resp.get("results", []):
            block_id = block["id"]
            if block.get("type") in preserved_types:
                preserved_ids.append(block_id)
                continue
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
        "preserved_block_count": len(preserved_ids),
        "appended_block_count": len(new_blocks),
        "appended": appended,
    }


@mcp.tool(
    name="upsert_page_by_property",
    description=(
        "Query a data source for a page matching a unique property value, "
        "then create or update accordingly. Returns {page_id, operation} "
        'where operation is "created", "updated", or "noop". '
        "For updates, only the provided properties are changed. "
        "When children blocks are provided: on create they are set as the page body; "
        "on update existing blocks are replaced (preserving child_database/child_page by default). "
        "Use this for deterministic contact/interaction sync."
    ),
)
async def upsert_page_by_property(
    data_source_id: str,
    match_property: str,
    match_property_type: str,
    match_value: str,
    properties: dict[str, Any],
    children: Optional[list[dict[str, Any]]] = None,
    preserve_block_types: Optional[list[str]] = None,
) -> dict[str, Any]:
    filter_condition = {match_property_type: {"equals": match_value}}
    query_filter = {"property": match_property, **filter_condition}

    result = await _client.request(
        "post",
        f"/v1/data_sources/{data_source_id}/query",
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
        response: dict[str, Any] = {"page_id": page_id, "operation": "updated", "page": updated}
        if children is not None:
            response["blocks"] = await _replace_blocks(page_id, children, preserve_block_types)
        return response

    create_body: dict[str, Any] = {
        "parent": {"type": "data_source_id", "data_source_id": data_source_id},
        "properties": properties,
    }
    if children:
        create_body["children"] = children
    created = await _client.request("post", "/v1/pages", json=create_body)
    return {"page_id": created["id"], "operation": "created", "page": created}


@mcp.tool(
    name="replace_page_blocks",
    description=(
        "Replace all blocks in a page body with new content. "
        "Deletes existing child blocks, then appends the new blocks. "
        "Preserves child_database and child_page blocks by default so dashboard databases are not trashed. "
        "Useful for syncing notes/transcription without appending duplicates."
    ),
)
async def replace_page_blocks(
    page_id: str,
    new_blocks: list[dict[str, Any]],
    preserve_block_types: Optional[list[str]] = None,
) -> dict[str, Any]:
    return await _replace_blocks(page_id, new_blocks, preserve_block_types)


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
