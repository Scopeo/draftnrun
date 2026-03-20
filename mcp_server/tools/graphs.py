"""Graph management tools (DAG editor operations).

Exposes the same operations as the front-end studio:
edit draft, save a version snapshot, publish to production, view history.
"""

import logging
from uuid import uuid4

from fastmcp import FastMCP

from mcp_server.client import api
from mcp_server.tools._factory import Param, ToolSpec, register_proxy_tools
from mcp_server.tools.context_tools import _get_auth

logger = logging.getLogger(__name__)

_P_PROJECT = Param("project_id", str, description="The project ID.")
_P_RUNNER = Param("graph_runner_id", str, description="The graph runner version ID.")
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
        name="publish_to_production",
        description=(
            "Publish a graph version to production.\n\n"
            "The supplied runner becomes the live production version that serves API "
            "requests, cron jobs, widgets, and other production-oriented surfaces. "
            "The backend also creates a fresh draft runner for continued editing; "
            "re-fetch the graph using the returned `draft_graph_runner_id` before "
            "making more changes."
        ),
        method="put",
        path=f"{_GRAPH_BASE}/env/production",
        path_params=(_P_PROJECT, _P_RUNNER),
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


def _strip_readonly_messages_overrides(graph_data: dict) -> list[str]:
    """Strip manual overrides of the readonly `messages` field.

    The `messages` input on AI Agent, AI (LLM Call), and similar components
    is readonly — it is auto-filled from the previous component via edge
    canonical port mapping. The frontend blocks editing this field; this
    function enforces the same constraint on the MCP side.

    Specifically: for any non-start node that has an incoming edge, we strip
    `input_port_instances` entries and `kind="input"` parameters targeting
    `messages`. Returns a list of human-readable warnings about what was stripped.
    """
    instances = graph_data.get("component_instances", [])
    edges = graph_data.get("edges", [])
    if not instances or not edges:
        return []

    edge_destinations = {e["destination"] for e in edges if "destination" in e}
    warnings: list[str] = []

    for instance in instances:
        instance_id = instance.get("id")
        if instance.get("is_start_node") or instance_id not in edge_destinations:
            continue

        ipi_list = instance.get("input_port_instances", [])
        original_len = len(ipi_list)
        instance["input_port_instances"] = [
            ipi for ipi in ipi_list if ipi.get("name") != "messages"
        ]
        if len(instance["input_port_instances"]) < original_len:
            name = instance.get("name") or instance.get("ref") or instance_id
            warnings.append(
                f"Stripped input_port_instances override for 'messages' on "
                f"'{name}': this field is readonly and auto-filled from the "
                f"previous component via the edge."
            )

        params = instance.get("parameters", [])
        cleaned_params = []
        for p in params:
            if p.get("name") == "messages" and p.get("kind") == "input":
                name = instance.get("name") or instance.get("ref") or instance_id
                warnings.append(
                    f"Stripped kind='input' parameter 'messages' on '{name}': "
                    f"this field is readonly and auto-filled via edge canonical mapping."
                )
                continue
            cleaned_params.append(p)
        instance["parameters"] = cleaned_params

    for w in warnings:
        logger.warning(w)

    return warnings


def register(mcp: FastMCP) -> None:
    register_proxy_tools(mcp, PROXY_SPECS)

    @mcp.tool()
    async def update_graph(project_id: str, graph_runner_id: str, graph_data: dict) -> dict:
        """Replace the full graph definition (PUT semantics).

        Safe pattern: `get_project_overview` -> `get_graph` -> modify -> `update_graph`.
        The `graph_runner_id` must be the true editable draft runner
        (`env='draft'` and untagged). The `graph_data` should include
        `component_instances`, `edges`, `port_mappings`, and `relationships`.

        New nodes and edges can have `id` set to null — a UUID is auto-generated
        before sending to the backend. You can also provide your own UUID for
        new nodes (useful when you need to reference the ID in edges,
        relationships, or field expressions within the same update).

        Readonly field enforcement: the `messages` input on AI Agent,
        AI (LLM Call), and similar components is readonly — it is auto-filled
        from the previous component's output via edge canonical port mapping.
        Any manual override (input_port_instances or kind='input' parameter)
        targeting `messages` on a node with an incoming edge is automatically
        stripped. Use `initial_prompt` to inject context into agents instead.

        Canonical port auto-mapping: the backend auto-generates PortMapping
        rows for every edge that lacks an explicit port_mapping, using the
        `is_canonical` flag on port_definitions. This means you do NOT need to
        inject `input_port_instances` or field expressions for canonical inputs
        like `markdown_content` (PDF), `query` (Retriever/Search), etc. —
        just create the edge and the backend handles the rest, exactly like the
        frontend does.

        Important constraints:
        - Save version creates an immutable snapshot and keeps the current draft.
        - Publish to production creates a fresh draft with new instance IDs.
        - Explicit `port_mappings` are still needed for non-canonical wiring.
        - Pure `port_mappings`-only edits are risky because current backend
          change detection excludes `port_mappings`.
        - Key-extraction refs like `@{{uuid.port::key}}` are safest through
          `input_port_instances`.

        Args:
            project_id: The project ID.
            graph_runner_id: The graph runner version ID (must be a draft).
            graph_data: Complete graph definition.
        """
        jwt, _ = _get_auth()
        graph_data = _assign_missing_ids(graph_data)
        key_warnings = _warn_unknown_graph_keys(graph_data)
        readonly_warnings = _strip_readonly_messages_overrides(graph_data)
        all_warnings = key_warnings + readonly_warnings
        result = await api.put(
            f"/projects/{project_id}/graph/{graph_runner_id}", jwt, json=graph_data
        )
        if all_warnings:
            if isinstance(result, dict):
                result["_mcp_warnings"] = all_warnings
            else:
                result = {"_mcp_response": result, "_mcp_warnings": all_warnings}
        return result
