"""Component catalog tools.

The release_stage is automatically applied from the org's assignment —
the AI cannot override it to see components above the org's tier.
"""

import logging
from typing import Annotated, Optional

from fastmcp import FastMCP
from pydantic import Field

from mcp_server.client import api
from mcp_server.context import require_org_context
from mcp_server.tools.context_tools import _get_auth

logger = logging.getLogger(__name__)


def _extract_ports(comp: dict) -> dict:
    """Extract input/output port names from a catalog component entry."""
    port_defs = comp.get("port_definitions") or comp.get("ports") or []
    if not port_defs:
        return {}
    input_ports = []
    output_ports = []
    for p in port_defs:
        port_name = p.get("name") or p.get("port_name")
        if not port_name:
            continue
        is_canonical = p.get("is_canonical", False)
        entry = {"name": port_name}
        if is_canonical:
            entry["canonical"] = True
        port_type = (p.get("port_type") or p.get("type") or "").upper()
        if port_type == "OUTPUT":
            output_ports.append(entry)
        elif port_type == "INPUT":
            input_ports.append(entry)
    result = {}
    if input_ports:
        result["input_ports"] = input_ports
    if output_ports:
        result["output_ports"] = output_ports
    return result


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    async def list_components() -> dict:
        """List all available component types from the catalog.

        Returns every component accessible to the organization (filtered by
        the org's release stage) with parameters, port definitions, categories,
        and cost info. Use this to discover component_id and component_version_id
        values when building or modifying graphs.
        """
        jwt, user_id = _get_auth()
        org = await require_org_context(user_id)
        release_stage = org.get("release_stage") or "public"
        return await api.get(f"/components/{org['org_id']}", jwt, trim=False, release_stage=release_stage)

    @mcp.tool()
    async def search_components(
        query: Annotated[str, Field(description="Search term to match against component name or description.")],
        category: Annotated[
            Optional[str],
            Field(
                description=(
                    "Optional category filter (e.g. 'AI', 'Workflow Logic', 'RAG', 'Search', "
                    "'SQL/Data', 'Integrations', 'Code', 'Files')."
                ),
            ),
        ] = None,
    ) -> list[dict]:
        """Search the component catalog by name or description.

        Returns a compact summary of matching components including port
        definitions (input/output port names needed for edges and field expressions
        in `update_graph`).
        """
        query = query.strip()
        if not query:
            raise ValueError("Search query must not be empty. Provide a term to match against component names.")

        jwt, user_id = _get_auth()
        org = await require_org_context(user_id)
        release_stage = org.get("release_stage") or "public"
        catalog = await api.get(
            f"/components/{org['org_id']}", jwt, trim=False, release_stage=release_stage,
        )

        components = catalog if isinstance(catalog, list) else catalog.get("components", [])
        query_lower = query.lower()

        results = []
        for comp in components:
            name = comp.get("name") or comp.get("component_name") or ""
            description = comp.get("description") or ""
            comp_category = comp.get("category") or ""

            if category and comp_category.lower() != category.lower():
                continue

            if query_lower in name.lower() or query_lower in description.lower():
                component_id = comp.get("component_id") or comp.get("id")
                component_version_id = comp.get("component_version_id") or comp.get("version_id")
                if not comp.get("component_id") or not comp.get("component_version_id"):
                    logger.warning(
                        "Component '%s' missing explicit component_id or component_version_id, "
                        "falling back to generic keys",
                        name,
                    )
                ports = _extract_ports(comp)
                results.append({
                    "name": name,
                    "category": comp_category,
                    "description": description[:200],
                    "component_id": component_id,
                    "component_version_id": component_version_id,
                    "function_callable": comp.get("function_callable", False),
                    "requires_integration": bool(comp.get("integration")),
                    "release_stage": comp.get("release_stage"),
                    **ports,
                })

        return results
