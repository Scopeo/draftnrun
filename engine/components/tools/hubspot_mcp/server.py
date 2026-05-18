"""
FastMCP server exposing HubSpot CRM tools over stdio.

Run:
    uv run python -m engine.components.tools.hubspot_mcp.server

Expects HUBSPOT_ACCESS_TOKEN in the environment.
"""

import warnings
from enum import Enum
from typing import Any, Literal, Optional

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    from fastmcp import FastMCP

from engine.components.tools.hubspot_mcp.client import HubSpotClient
from engine.components.tools.hubspot_mcp.schema import (
    Association,
    AssocType,
    CompanyProperties,
    ContactProperties,
    EmailProperties,
    FilterGroup,
    NoteProperties,
    TaskProperties,
)
from engine.components.types import ToolDescription
from engine.llm_services.utils import resolve_schema_refs

mcp = FastMCP("hubspot-crm")
_client: HubSpotClient  # assigned in __main__ before mcp.run()


class Tag(str, Enum):
    auth = "auth"
    contacts = "contacts"
    companies = "companies"
    engagements = "engagements"
    associations = "associations"


@mcp.tool(
    name="auth_get_current_user",
    description=(
        "Retrieve the HubSpot user and account associated with the current access token. "
        "Returns the user's email, user ID, hub ID, and hub domain. "
        "Use this to identify who is the owner making requests."
    ),
    tags={Tag.auth},
)
async def auth_get_current_user() -> dict[str, Any]:
    return await _client.get_token_hubspot_metadata()


@mcp.tool(name="crm_create_contact", description="Create a new HubSpot contact.", tags={Tag.contacts})
async def crm_create_contact(
    properties: ContactProperties,
    associations: Optional[list[Association]] = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {"properties": properties.model_dump(exclude_none=True)}
    if associations:
        body["associations"] = [a.model_dump() for a in associations]
    return await _client.request("post", "/crm/v3/objects/contacts", json=body)


@mcp.tool(name="crm_update_contact", description="Update an existing HubSpot contact by ID.", tags={Tag.contacts})
async def crm_update_contact(
    objectId: str,
    properties: ContactProperties,
) -> dict[str, Any]:
    body = {"properties": properties.model_dump(exclude_none=True)}
    return await _client.request("patch", f"/crm/v3/objects/contacts/{objectId}", json=body)


@mcp.tool(name="crm_search_contacts", description="Search HubSpot contacts using filter groups.", tags={Tag.contacts})
async def crm_search_contacts(
    filterGroups: list[FilterGroup],
    properties: Optional[list[str]] = None,
    limit: int = 10,
    after: Optional[str] = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "filterGroups": [fg.model_dump() for fg in filterGroups],
        "limit": limit,
    }
    if properties:
        body["properties"] = properties
    if after:
        body["after"] = after
    return await _client.request("post", "/crm/v3/objects/contacts/search", json=body)


@mcp.tool(name="crm_get_contact", description="Get a HubSpot contact by ID.", tags={Tag.contacts})
async def crm_get_contact(
    objectId: str,
    properties: Optional[list[str]] = None,
) -> dict[str, Any]:
    params: dict[str, Any] = {}
    if properties:
        params["properties"] = ",".join(properties)
    return await _client.request("get", f"/crm/v3/objects/contacts/{objectId}", params=params)


@mcp.tool(name="crm_create_company", description="Create a new HubSpot company.", tags={Tag.companies})
async def crm_create_company(
    properties: CompanyProperties,
    associations: Optional[list[Association]] = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {"properties": properties.model_dump(exclude_none=True)}
    if associations:
        body["associations"] = [a.model_dump() for a in associations]
    return await _client.request("post", "/crm/v3/objects/companies", json=body)


@mcp.tool(name="crm_update_company", description="Update an existing HubSpot company by ID.", tags={Tag.companies})
async def crm_update_company(
    objectId: str,
    properties: CompanyProperties,
) -> dict[str, Any]:
    body = {"properties": properties.model_dump(exclude_none=True)}
    return await _client.request("patch", f"/crm/v3/objects/companies/{objectId}", json=body)


@mcp.tool(
    name="crm_search_companies",
    description="Search HubSpot companies using filter groups.",
    tags={Tag.companies},
)
async def crm_search_companies(
    filterGroups: list[FilterGroup],
    properties: Optional[list[str]] = None,
    limit: int = 10,
    after: Optional[str] = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "filterGroups": [fg.model_dump() for fg in filterGroups],
        "limit": limit,
    }
    if properties:
        body["properties"] = properties
    if after:
        body["after"] = after
    return await _client.request("post", "/crm/v3/objects/companies/search", json=body)


@mcp.tool(
    name="crm_get_company",
    description="Get a HubSpot company by ID.",
    tags={Tag.companies},
)
async def crm_get_company(
    objectId: str,
    properties: Optional[list[str]] = None,
) -> dict[str, Any]:
    params: dict[str, Any] = {}
    if properties:
        params["properties"] = ",".join(properties)
    return await _client.request("get", f"/crm/v3/objects/companies/{objectId}", params=params)


@mcp.tool(
    name="notes_create",
    description=(
        "Create a note engagement in HubSpot. Use inline associations to link to a "
        "contact (typeId 202) or company (typeId 190)."
    ),
    tags={Tag.engagements},
)
async def notes_create(
    properties: NoteProperties,
    associations: Optional[list[Association]] = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {"properties": properties.model_dump(exclude_none=True)}
    if associations:
        body["associations"] = [a.model_dump() for a in associations]
    return await _client.request("post", "/crm/v3/objects/notes", json=body)


@mcp.tool(
    name="crm_upsert_contact_by_email",
    description=(
        "Create or update a HubSpot contact by email. If objectId is provided, update that "
        "contact directly; otherwise use HubSpot's native create-or-update-by-email endpoint."
    ),
    tags={Tag.contacts},
)
async def crm_upsert_contact_by_email(
    properties: ContactProperties,
    objectId: Optional[str] = None,
) -> dict[str, Any]:
    payload = properties.model_dump(exclude_none=True)

    if objectId:
        result = await _client.request("patch", f"/crm/v3/objects/contacts/{objectId}", json={"properties": payload})
        return {"id": result.get("id", objectId), "operation": "updated"}

    email = payload.get("email")
    if not email:
        raise ValueError("crm_upsert_contact_by_email requires properties.email when objectId is not provided")

    legacy_payload = [
        {"property": key, "value": value}
        for key, value in payload.items()
    ]
    result = await _client.request("post", f"/contacts/v1/contact/createOrUpdate/email/{email}", json={"properties": legacy_payload})

    vid = result.get("vid")
    if vid is None and isinstance(result.get("canonical-vid"), int):
        vid = result["canonical-vid"]
    if vid is None and isinstance(result.get("canonical-vid"), str):
        vid = result["canonical-vid"]

    is_new = bool(result.get("isNew"))
    operation = "created" if is_new else "updated"
    return {"id": str(vid) if vid is not None else "", "operation": operation}


@mcp.tool(
    name="notes_upsert_for_contact",
    description=(
        "Create or update a HubSpot note for a contact. If objectId is provided, update that note; "
        "otherwise create a new note associated to the contact. Can skip the call when the body is empty."
    ),
    tags={Tag.engagements},
)
async def notes_upsert_for_contact(
    contactId: str,
    properties: NoteProperties,
    objectId: Optional[str] = None,
    associationTypeId: int = 202,
    skipIfBodyEmpty: bool = False,
) -> dict[str, Any]:
    payload = properties.model_dump(exclude_none=True)
    note_body = payload.get("hs_note_body", "")

    if skipIfBodyEmpty and not str(note_body).strip():
        return {"id": "", "operation": "skipped", "contactId": contactId}

    if objectId:
        result = await _client.request("patch", f"/crm/v3/objects/notes/{objectId}", json={"properties": payload})
        return {"id": result.get("id", objectId), "operation": "updated", "contactId": contactId}

    associations = [
        {
            "to": {"id": contactId},
            "types": [
                {
                    "associationCategory": "HUBSPOT_DEFINED",
                    "associationTypeId": associationTypeId,
                }
            ],
        }
    ]
    result = await _client.request(
        "post",
        "/crm/v3/objects/notes",
        json={"properties": payload, "associations": associations},
    )
    return {"id": result.get("id", ""), "operation": "created", "contactId": contactId}


@mcp.tool(
    name="emails_create",
    description=(
        "Log an email engagement in HubSpot's timeline (does NOT send a real email). "
        "Use hs_email_headers (JSON string) to set sender and recipient — "
        "hs_email_from_email and hs_email_to_email are read-only and must NOT be used. "
        "Use inline associations to link to a contact (typeId 198) or company (typeId 186)."
    ),
    tags={Tag.engagements},
)
async def emails_create(
    properties: EmailProperties,
    associations: Optional[list[Association]] = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {"properties": properties.model_dump(exclude_none=True)}
    if associations:
        body["associations"] = [a.model_dump() for a in associations]
    return await _client.request("post", "/crm/v3/objects/emails", json=body)


@mcp.tool(
    name="tasks_create",
    description=(
        "Create a task engagement in HubSpot. "
        "hs_task_type is required (TODO/EMAIL/CALL). "
        "Use inline associations to link to a contact (typeId 204) or company (typeId 192)."
    ),
    tags={Tag.engagements},
)
async def tasks_create(
    properties: TaskProperties,
    associations: Optional[list[Association]] = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {"properties": properties.model_dump(exclude_none=True)}
    if associations:
        body["associations"] = [a.model_dump() for a in associations]
    return await _client.request("post", "/crm/v3/objects/tasks", json=body)


@mcp.tool(
    name="crm_create_association",
    description=(
        "Create an association between two existing HubSpot CRM objects "
        "(e.g. contact <-> company). For engagements (notes, tasks, emails) use "
        "inline associations in the create call instead."
    ),
    tags={Tag.associations},
)
async def crm_create_association(
    fromObjectType: Literal["companies", "contacts", "deals", "tickets", "products", "line_items", "quotes"],
    toObjectType: Literal["companies", "contacts", "deals", "tickets", "products", "line_items", "quotes"],
    fromObjectId: str,
    toObjectId: str,
    associationTypes: list[AssocType],
) -> dict[str, Any]:
    body = [t.model_dump() for t in associationTypes]
    return await _client.request(
        "put",
        f"/crm/v4/objects/{fromObjectType}/{fromObjectId}/associations/{toObjectType}/{toObjectId}",
        json=body,
    )


@mcp.tool(
    name="crm_list_association_types",
    description=(
        "List all association type labels between two HubSpot object types "
        "(e.g. contacts <-> companies). Use this to discover the correct associationTypeId."
    ),
    tags={Tag.associations},
)
async def crm_list_association_types(
    fromObjectType: str,
    toObjectType: str,
) -> dict[str, Any]:
    return await _client.request(
        "get",
        f"/crm/v4/associations/{fromObjectType}/{toObjectType}/labels",
    )


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

    token = os.environ.get("HUBSPOT_ACCESS_TOKEN")
    if not token:
        raise RuntimeError("HUBSPOT_ACCESS_TOKEN environment variable is required")

    _client = HubSpotClient(token)
    mcp.run(show_banner=False)
