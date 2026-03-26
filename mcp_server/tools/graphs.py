"""Graph management tools (DAG editor operations).

Exposes the same operations as the front-end studio:
edit draft, save a version snapshot, publish to production, view history.
"""

import logging
from typing import Annotated
from uuid import UUID, uuid4

from fastmcp import FastMCP
from pydantic import Field

from mcp_server.client import ToolError, api
from mcp_server.tools._factory import Param, ToolSpec, register_proxy_tools
from mcp_server.tools.context_tools import _get_auth

logger = logging.getLogger(__name__)

_P_PROJECT = Param("project_id", UUID, description="The project ID (from list_projects or get_project_overview).")
_P_RUNNER = Param("graph_runner_id", UUID, description="The graph runner version ID (from get_project_overview).")
_GRAPH_BASE = "/projects/{project_id}/graph/{graph_runner_id}"

PROXY_SPECS: list[ToolSpec] = [
    ToolSpec(
        name="get_graph",
        description=(
            "Get the full graph (DAG) for a project version.\n\n"
            "Returns the full, untrimmed payload so it can be safely round-tripped "
            "through update_graph. Includes component_instances (nodes), edges "
            "(execution order), port_mappings (data flow), relationships (nesting), "
            "and playground_input_schema. See `docs://graphs`, `docs://versioning`, "
            "and `docs://known-quirks` for the full safety model."
        ),
        method="get",
        path=_GRAPH_BASE,
        path_params=(_P_PROJECT, _P_RUNNER),
        trim=False,
    ),
    ToolSpec(
        name="save_graph_version",
        description=(
            "Save the current graph state as a named version snapshot.\n\n"
            "Creates an immutable tagged copy of the current draft that can be "
            "referenced later via get_graph_history. The current draft runner stays "
            "editable and keeps the same instance IDs."
        ),
        method="post",
        path=f"{_GRAPH_BASE}/save-version",
        path_params=(_P_PROJECT, _P_RUNNER),
    ),
    ToolSpec(
        name="promote_version_to_env",
        description=(
            "Promote a tagged version to an environment (low-level).\n\n"
            "Rebinds an existing graph runner to the specified environment. "
            "This does NOT tag, clone, or create a new draft runner — it only "
            "moves the env pointer.\n\n"
            "⚠️ Do NOT call this on the editable draft. Use `publish_to_production` "
            "to deploy the draft (which tags, promotes, and creates a fresh draft). "
            "This tool is for advanced scenarios like rolling back production to a "
            "previously tagged version."
        ),
        method="put",
        path=f"{_GRAPH_BASE}/env/{{env}}",
        path_params=(
            _P_PROJECT,
            _P_RUNNER,
            Param("env", str, description="Target environment: 'production' or 'draft'."),
        ),
    ),
    ToolSpec(
        name="get_graph_history",
        description="Get the modification history and saved versions of a graph.",
        method="get",
        path=f"{_GRAPH_BASE}/modification-history",
        path_params=(_P_PROJECT, _P_RUNNER),
    ),
]


def _assign_missing_ids(graph_data: dict) -> dict:
    """Auto-generate UUIDs for component instances and edges that have id=null.

    The backend requires non-null IDs on both component instances (for
    field-expression keying) and edges (for persistence). This pre-processing
    step makes ``id: null`` safe for callers by generating UUIDs before the
    payload reaches the backend.
    """
    for key in ("component_instances", "edges"):
        items = graph_data.get(key)
        if not items:
            continue
        for item in items:
            if not item.get("id"):
                item["id"] = str(uuid4())

    return graph_data


_KNOWN_GRAPH_KEYS = {
    "component_instances", "edges", "port_mappings", "relationships",
    "playground_input_schema", "playground_field_types",
}

_LIKELY_TYPOS: dict[str, str] = {
    "ports_mappings": "port_mappings",
    "port_mapping": "port_mappings",
    "portmappings": "port_mappings",
    "components": "component_instances",
    "component_instance": "component_instances",
    "nodes": "component_instances",
    "relationship": "relationships",
    "edge": "edges",
}


def _warn_unknown_graph_keys(graph_data: dict) -> list[str]:
    """Warn about unrecognised top-level keys in graph_data (likely typos)."""
    unknown = set(graph_data.keys()) - _KNOWN_GRAPH_KEYS
    if not unknown:
        return []

    warnings: list[str] = []
    for key in sorted(unknown):
        suggestion = _LIKELY_TYPOS.get(key)
        if suggestion:
            warnings.append(
                f"Unknown graph key '{key}' — did you mean '{suggestion}'? "
                f"The key was ignored by the backend."
            )
        else:
            warnings.append(
                f"Unknown graph key '{key}' — expected keys are: "
                f"{', '.join(sorted(_KNOWN_GRAPH_KEYS))}. "
                f"The key was passed through but may be silently ignored."
            )
    for w in warnings:
        logger.warning(w)
    return warnings


_OAUTH_KEYWORDS = ("access_token", "oauth", "integration", "credentials")


def _enrich_graph_update_error(message: str) -> str:
    # TODO: temporary keyword matching on error strings — replace with structured error codes from the backend
    """Add actionable next-step guidance to update_graph backend errors."""
    lower = message.lower()
    if any(kw in lower for kw in _OAUTH_KEYWORDS):
        return (
            f"{message} | This usually means the graph contains an integration-backed "
            "component (e.g. Gmail, Slack, HubSpot) whose OAuth connection is not set up. "
            "Next steps: 1) list_oauth_connections() — check which connections exist, "
            "2) the user must connect the integration in the Draft'n Run web UI "
            "(MCP cannot initiate OAuth flows), "
            "3) retry update_graph once the connection is active. "
            "See docs://integrations for details."
        )
    if "not found" in lower or "does not exist" in lower:
        return (
            f"{message} | Next step: verify IDs with get_project_overview(project_id) "
            "and get_graph(project_id, graph_runner_id) — the draft runner may have "
            "changed after a publish."
        )
    return message


def register(mcp: FastMCP) -> None:
    register_proxy_tools(mcp, PROXY_SPECS)

    @mcp.tool()
    async def publish_to_production(
        project_id: Annotated[
            UUID, Field(description="The project ID (from list_projects or get_project_overview).")
        ],
        graph_runner_id: Annotated[
            UUID, Field(description="The editable draft runner ID (from get_project_overview).")
        ],
    ) -> dict:
        """Publish the current draft to production (full deploy).

        Tags the current draft with an auto-incremented version, promotes it to the
        live production environment, and creates a brand-new draft runner for continued
        editing.

        Returns `draft_graph_runner_id` (the new editable draft) and
        `prod_graph_runner_id` (now serving production). Always switch to
        `draft_graph_runner_id` and call `get_graph` before making further edits.

        The supplied `graph_runner_id` must be the current editable draft
        (env='draft', untagged).
        """
        jwt, _ = _get_auth()
        return await api.post(
            f"/projects/{project_id}/graph/{graph_runner_id}/deploy", jwt
        )

    @mcp.tool()
    async def get_draft_graph(
        project_id: Annotated[UUID, Field(description="The project ID (from list_projects or get_project_overview).")],
    ) -> dict:
        """Get the full graph for a project's editable draft — resolves the draft runner automatically.

        Convenience wrapper that avoids passing ``graph_runner_id`` directly.
        Internally fetches the project, finds the editable draft runner
        (env='draft', untagged), and returns the full untrimmed graph along
        with the resolved ``graph_runner_id``.

        Use this when you need the current draft but don't have the
        ``graph_runner_id`` handy.  For production graphs or specific tagged
        versions, use ``get_graph`` with an explicit runner ID.
        """
        jwt, _ = _get_auth()
        project = await api.get(f"/projects/{project_id}", jwt)

        draft = None
        for gr in project.get("graph_runners", []):
            if gr.get("env") == "draft" and gr.get("tag_name") is None:
                draft = gr
                break

        if not draft:
            raise ToolError(
                f"No editable draft runner found for project {project_id}. "
                "The project may not have been published yet or may lack a draft. "
                "Use get_project_overview(project_id) to inspect all runners."
            )

        runner_id = draft.get("graph_runner_id") or draft.get("id")
        graph = await api.get(
            f"/projects/{project_id}/graph/{runner_id}", jwt, trim=False
        )
        return {
            "graph_runner_id": runner_id,
            "graph": graph,
        }

    @mcp.tool()
    async def update_graph(
        project_id: Annotated[
            UUID, Field(description="The project ID (from list_projects or get_project_overview).")
        ],
        graph_runner_id: Annotated[
            UUID,
            Field(description="The graph runner version ID — must be a draft (from get_project_overview)."),
        ],
        graph_data: Annotated[
            dict,
            Field(description="Complete graph definition (component_instances, edges, port_mappings, relationships)."),
        ],
    ) -> dict:
        """Replace the full graph definition (PUT semantics).

        ⚠️ REQUIRED: Call `get_guide('graphs')` before using this tool for the
        first time in a session. The guide contains edge format, field expression
        format, and canonical port rules that are critical for a successful call.

        ⚠️ CONCURRENT EDIT WARNING: If the project is open in the Draft'n Run
        web UI, the browser may overwrite API changes (last-write-wins, no
        conflict detection). Close the browser tab before calling this tool.

        Safe pattern: `get_project_overview` -> `get_graph` -> modify -> `update_graph`.
        The `graph_runner_id` must be the true editable draft runner
        (`env='draft'` and untagged). The `graph_data` should include
        `component_instances`, `edges`, `port_mappings`, and `relationships`.

        New nodes and edges can have `id` set to null — a UUID is auto-generated
        before sending to the backend. You can also provide your own UUID for
        new nodes (useful when you need to reference the ID in edges,
        relationships, or field expressions within the same update).

        Canonical port auto-wiring: the backend auto-generates a PortMapping
        **and** a visible RefNode field expression for every edge whose
        canonical input has no user-provided expression. This means you do NOT
        need to inject `input_port_instances` or field expressions for
        canonical inputs like `messages` (AI Agent), `markdown_content` (PDF),
        `query` (Retriever/Search), etc. — just create the edge and the
        backend handles the rest. The auto-generated expression (e.g.
        `@{{<source_uuid>.output}}`) is returned in
        `auto_generated_field_expressions` and is visible and editable by the
        user. If you provide your own field expression for a canonical input,
        the backend respects it and skips auto-generation.

        Important constraints:
        - Save version creates an immutable snapshot and keeps the current draft.
        - Publish to production creates a fresh draft with new instance IDs.
        - Explicit `port_mappings` are still needed for non-canonical wiring.
        - Pure `port_mappings`-only edits are risky because current backend
          change detection excludes `port_mappings`.
        - Key-extraction refs like `@{{uuid.port::key}}` are safest through
          `input_port_instances`.
        - `get_graph` returns `field_expressions` (normalized read format).
          When writing, use `input_port_instances` on component instances —
          do NOT copy `field_expressions` from `get_graph` into `update_graph`.
        """
        jwt, _ = _get_auth()
        graph_data = _assign_missing_ids(graph_data)
        warnings = _warn_unknown_graph_keys(graph_data)
        try:
            result = await api.put(
                f"/projects/{project_id}/graph/{graph_runner_id}", jwt, json=graph_data
            )
        except ToolError as exc:
            raise ToolError(_enrich_graph_update_error(str(exc))) from exc
        if warnings:
            if isinstance(result, dict):
                result["_mcp_warnings"] = warnings
            else:
                result = {"_mcp_response": result, "_mcp_warnings": warnings}
        return result

    @mcp.tool()
    async def update_component_parameters(
        project_id: Annotated[
            UUID, Field(description="The project ID (from list_projects or get_project_overview).")
        ],
        graph_runner_id: Annotated[
            UUID,
            Field(description="The graph runner version ID — must be a draft (from get_project_overview)."),
        ],
        component_instance_id: Annotated[
            UUID,
            Field(
                description="The ID of the component instance to update"
                " (from get_graph — each node has an 'id' field)."
            ),
        ],
        parameters: Annotated[
            dict,
            Field(description='Dict of parameter names to new values. Only provided keys are updated.'),
        ],
    ) -> dict:
        """Update specific parameters on a single component instance within a graph.

        Performs a server-side read-modify-write: fetches the current graph,
        merges the provided parameters into the target component, and saves
        the full graph back. Only the parameter keys you provide are changed —
        all other parameters and the rest of the graph are preserved.

        This is the recommended tool for single-parameter changes on workflow
        components (e.g. updating an AI Agent's ``initial_prompt`` or a
        Retriever's ``prompt_template``). It avoids the need to send the full
        graph payload through ``update_graph``.

        ⚠️ Do NOT use this tool to modify fields with ``drives_output_schema``
        (e.g. ``payload_schema`` on Start, ``output_format`` on AI Agent)
        unless you intend to change the component's dynamic output ports.
        Changing these fields will delete and recreate output port instances,
        which may break downstream field expressions.
        """
        jwt, _ = _get_auth()

        graph = await api.get(
            f"/projects/{project_id}/graph/{graph_runner_id}", jwt, trim=False
        )

        instances = graph.get("component_instances", [])
        target = None
        cid_str = str(component_instance_id)
        for inst in instances:
            if inst.get("id") == cid_str:
                target = inst
                break
        if not target:
            instance_ids = [inst.get("id") for inst in instances]
            raise ToolError(
                f"Component instance '{component_instance_id}' not found in graph. "
                f"Available instance IDs: {instance_ids}"
            )

        existing_params = target.get("parameters", [])
        updated_names = set()
        for param in existing_params:
            if param.get("name") in parameters:
                param["value"] = parameters[param["name"]]
                updated_names.add(param["name"])

        missing = set(parameters.keys()) - updated_names
        if missing:
            available = [p.get("name") for p in existing_params]
            raise ToolError(
                f"Parameter(s) {sorted(missing)} not found on component "
                f"'{target.get('name', component_instance_id)}'. "
                f"Available parameters: {available}"
            )

        graph_data = {
            "component_instances": instances,
            "edges": graph.get("edges", []),
            "port_mappings": graph.get("port_mappings", []),
            "relationships": graph.get("relationships", []),
        }
        if graph.get("playground_input_schema") is not None:
            graph_data["playground_input_schema"] = graph["playground_input_schema"]
        if graph.get("playground_field_types") is not None:
            graph_data["playground_field_types"] = graph["playground_field_types"]
        try:
            await api.put(
                f"/projects/{project_id}/graph/{graph_runner_id}", jwt, json=graph_data
            )
        except ToolError as exc:
            raise ToolError(_enrich_graph_update_error(str(exc))) from exc

        return {
            "status": "ok",
            "component": target.get("name", component_instance_id),
            "updated_parameters": sorted(updated_names),
        }
