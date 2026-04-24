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
_P_INSTANCE = Param(
    "instance_id", UUID, description="The component instance ID (from get_graph or get_graph_v2)."
)
_GRAPH_BASE = "/projects/{project_id}/graph/{graph_runner_id}"
_GRAPH_BASE_V2 = "/v2/projects/{project_id}/graph/{graph_runner_id}"

PROXY_SPECS: list[ToolSpec] = [
    ToolSpec(
        name="get_graph",
        description=(
            "Get the full graph (DAG) for a project version.\n\n"
            "Returns the full, untrimmed payload so it can be safely round-tripped "
            "through update_graph. Includes component_instances (nodes), edges "
            "(execution order), relationships (nesting), "
            "and playground_input_schema. See `docs://graphs`, `docs://versioning`, "
            "and `docs://known-quirks` for the full safety model."
        ),
        method="get",
        path=_GRAPH_BASE,
        path_params=(_P_PROJECT, _P_RUNNER),
        trim=False,
    ),
    ToolSpec(
        name="get_graph_v2",
        description=(
            "Get the graph using the file-based v2 format.\n\n"
            "Returns top-level graph info only in graph_map nodes, where each node "
            "includes file_key, instance_id, and label. "
            "Node references in edges can use id or file_key."
        ),
        method="get",
        path=_GRAPH_BASE_V2,
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
    ToolSpec(
        name="create_component_v2",
        description=(
            "Create a new component instance in a graph (v2).\n\n"
            "Adds a single component to the draft graph. Returns the new instance_id. "
            "After creation, use update_graph_topology_v2 to connect it with edges."
        ),
        method="post",
        path=f"{_GRAPH_BASE_V2}/components",
        path_params=(_P_PROJECT, _P_RUNNER),
        body_param=Param(
            "component_data",
            dict,
            description=(
                "Component definition: {component_id, component_version_id, label, "
                "is_start_node, parameters, input_port_instances, ...}."
            ),
        ),
    ),
    ToolSpec(
        name="update_component_v2",
        description=(
            "Update a single component instance's parameters and ports (v2).\n\n"
            "Only updates the specified component — does not touch topology. "
            "Optionally update label and is_start_node.\n\n"
            "⚠️ FULL-REPLACE semantics: `parameters` and `input_port_instances` "
            "replace the existing lists entirely. You MUST include ALL parameters "
            "from `get_graph` or `get_graph_v2`, not only the ones you want to "
            "change — omitted parameters will be lost. For single-parameter "
            "changes, prefer `update_component_parameters` which handles the "
            "read-modify-write automatically."
        ),
        method="put",
        path=f"{_GRAPH_BASE_V2}/components/{{instance_id}}",
        path_params=(_P_PROJECT, _P_RUNNER, _P_INSTANCE),
        body_param=Param(
            "component_data",
            dict,
            description=(
                "Component update: {parameters, input_port_instances, label?, is_start_node?, ...}. "
                "parameters and input_port_instances use full-replace — include the complete lists."
            ),
        ),
    ),
    ToolSpec(
        name="delete_component_v2",
        description=(
            "Delete a component instance from a graph (v2).\n\n"
            "Removes the component, its node, and cascades deletion of edges "
            "and relationships referencing it."
        ),
        method="delete",
        path=f"{_GRAPH_BASE_V2}/components/{{instance_id}}",
        path_params=(_P_PROJECT, _P_RUNNER, _P_INSTANCE),
    ),
    ToolSpec(
        name="update_graph_topology_v2",
        description=(
            "Update graph topology: edges, relationships, and node metadata (v2).\n\n"
            "⚠️ REQUIRED: Call `get_guide('graphs')` before using this tool for the "
            "first time in a session. The guide contains edge format and topology rules "
            "that are critical for a successful call.\n\n"
            "⚠️ CONCURRENT EDIT WARNING: If the project is open in the Draft'n Run "
            "web UI, the browser may overwrite API changes (last-write-wins). "
            "Close the browser tab before calling this tool.\n\n"
            "This tool mutates the draft graph and uses full-replace edge semantics — "
            "edges not in the payload are deleted. Always send the complete set of edges "
            "to avoid partial-topology writes and autosave races.\n\n"
            "All referenced instance_ids must already exist in the graph."
        ),
        method="put",
        path=f"{_GRAPH_BASE_V2}/map",
        path_params=(_P_PROJECT, _P_RUNNER),
        body_param=Param(
            "topology_data",
            dict,
            description=(
                "Topology payload: {nodes: [{instance_id, label, is_start_node}], "
                "edges: [{from: {id}, to: {id}, order?}], "
                "relationships: [{parent: {id}, child: {id}, parameter_name, order?}]}."
            ),
        ),
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
    "component_instances",
    "edges",
    "relationships",
    "playground_input_schema",
    "playground_field_types",
}

_LIKELY_TYPOS: dict[str, str] = {
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
                f"Unknown graph key '{key}' — did you mean '{suggestion}'? The key was ignored by the backend."
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


def _validate_component_instances(graph_data: dict) -> None:
    if not isinstance(graph_data, dict):
        raise ToolError(
            f"graph_data must be a dict, got {type(graph_data).__name__}. Pass the full graph object from get_graph."
        )
    instances = graph_data.get("component_instances", [])
    if not isinstance(instances, list):
        raise ToolError(
            f"component_instances must be a list, got {type(instances).__name__}. "
            "Pass the full graph object from get_graph."
        )
    for inst in instances:
        if not isinstance(inst, dict):
            raise ToolError(
                f"Each component_instance must be a dict, got {type(inst).__name__}: {inst!r:.100}. "
                "Pass the full graph object from get_graph."
            )
        if not inst.get("component_version_id"):
            name = inst.get("name") or inst.get("id") or "unknown"
            raise ToolError(
                f"Component '{name}' is missing 'component_version_id'. "
                "Each component_instance must include component_version_id from the catalog. "
                "Use list_components or search_components to find the correct ID, "
                "or start from get_graph to preserve existing values."
            )


def _convert_field_expressions_to_write_format(instances: list[dict]) -> None:
    """Convert read-format field_expressions into write-format input_port_instances.

    GET returns expressions in a top-level ``field_expressions`` list per instance,
    but PUT only processes ``input_port_instances``.  Without this conversion,
    complex expressions (e.g. json_build) whose ``value`` field is a lossy
    placeholder get silently corrupted on round-trip.
    """
    for inst in instances:
        field_expr_list = inst.pop("field_expressions", None)
        if not field_expr_list:
            continue

        input_port_instances = inst.setdefault("input_port_instances", [])
        existing_input_port_instance_names = {
            input_port_instance["name"]
            for input_port_instance in input_port_instances
            if "name" in input_port_instance
        }

        for field_expr in field_expr_list:
            field_name = field_expr.get("field_name")
            expression_json = field_expr.get("expression_json")
            if not field_name or not expression_json:
                continue
            if field_name in existing_input_port_instance_names:
                continue
            input_port_instances.append({
                "name": field_name,
                "field_expression": {"expression_json": expression_json},
            })


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
    if "not found in component definitions" in lower or ("parameter" in lower and "not found" in lower):
        return (
            f"{message} | The graph references a parameter that doesn't exist on the component's "
            "current version. This usually means a component was updated or the parameter name is wrong. "
            "Next step: call get_graph() to see the current component parameters, then rebuild your payload."
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
        project_id: Annotated[UUID, Field(description="The project ID (from list_projects or get_project_overview).")],
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
        return await api.post(f"/projects/{project_id}/graph/{graph_runner_id}/deploy", jwt)

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
        graph = await api.get(f"/projects/{project_id}/graph/{runner_id}", jwt, trim=False)
        return {
            "graph_runner_id": runner_id,
            "graph": graph,
        }

    @mcp.tool()
    async def update_graph(
        project_id: Annotated[UUID, Field(description="The project ID (from list_projects or get_project_overview).")],
        graph_runner_id: Annotated[
            UUID,
            Field(description="The graph runner version ID — must be a draft (from get_project_overview)."),
        ],
        graph_data: Annotated[
            dict,
            Field(description="Complete graph definition (component_instances, edges, relationships)."),
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
        (`env='draft'` and untagged).         The `graph_data` should include
        `component_instances`, `edges`, and `relationships`.

        New nodes and edges can have `id` set to null — a UUID is auto-generated
        before sending to the backend. You can also provide your own UUID for
        new nodes (useful when you need to reference the ID in edges,
        relationships, or field expressions within the same update).

        Canonical port auto-wiring: the backend auto-generates a visible RefNode
        field expression for every edge whose canonical input has no user-provided
        expression. This means you do NOT need to inject `input_port_instances`
        or field expressions for canonical inputs like `messages` (AI Agent),
        `markdown_content` (PDF), `query` (Retriever/Search), etc. — just create
        the edge and the backend handles the rest. The auto-generated expression
        (e.g. `@{{<source_uuid>.output}}`) is returned in
        `auto_generated_field_expressions` and is visible and editable by the
        user. If you provide your own field expression for a canonical input,
        the backend respects it and skips auto-generation.

        Important constraints:
        - Save version creates an immutable snapshot and keeps the current draft.
        - Publish to production creates a fresh draft with new instance IDs.
        - Key-extraction refs like `@{{uuid.port::key}}` are safest through
          `input_port_instances`.
        - `get_graph` returns `field_expressions` (normalized read format).
          When writing, use `input_port_instances` on component instances —
          do NOT copy `field_expressions` from `get_graph` into `update_graph`.
        """
        jwt, _ = _get_auth()
        _validate_component_instances(graph_data)
        try:
            graph_data = _assign_missing_ids(graph_data)
        except (TypeError, AttributeError) as exc:
            raise ToolError(f"Malformed graph_data: {exc}. Pass the full graph object from get_graph.") from exc
        warnings = _warn_unknown_graph_keys(graph_data)
        try:
            result = await api.put(f"/projects/{project_id}/graph/{graph_runner_id}", jwt, json=graph_data)
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
        project_id: Annotated[UUID, Field(description="The project ID (from list_projects or get_project_overview).")],
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
            Field(description="Dict of parameter names to new values. Only provided keys are updated."),
        ],
    ) -> dict:
        """Update specific parameters on a single component instance within a graph.

        Fetches the current graph, merges the provided parameters into the
        target component, and saves via the V2 single-component endpoint.
        Only the parameter keys you provide are changed — all other parameters
        and the rest of the graph are preserved.

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

        graph = await api.get(f"/projects/{project_id}/graph/{graph_runner_id}", jwt, trim=False)

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

        field_expr_list = target.get("field_expressions", [])
        for param in existing_params:
            if param.get("kind") != "input" or param.get("name") not in parameters:
                continue
            new_value = parameters[param["name"]]
            field_name = param["name"]
            existing_fe = next((fe for fe in field_expr_list if fe.get("field_name") == field_name), None)
            existing_type = (existing_fe or {}).get("expression_json", {}).get("type")
            if existing_fe is not None and existing_type not in (None, "literal"):
                continue
            if new_value is not None:
                expr = {"type": "literal", "value": str(new_value)}
                if existing_fe:
                    existing_fe["expression_json"] = expr
                    existing_fe["expression_text"] = str(new_value)
                else:
                    field_expr_list.append({
                        "field_name": field_name,
                        "expression_json": expr,
                        "expression_text": str(new_value),
                    })
            elif existing_fe:
                field_expr_list.remove(existing_fe)
        target["field_expressions"] = field_expr_list

        write_params = [p for p in existing_params if p.get("kind", "parameter") != "input"]

        _convert_field_expressions_to_write_format([target])
        input_port_instances = target.get("input_port_instances", [])

        component_data = {
            "parameters": write_params,
            "input_port_instances": input_port_instances,
        }

        v2_path = (
            f"/v2/projects/{project_id}/graph/{graph_runner_id}"
            f"/components/{component_instance_id}"
        )
        try:
            await api.put(v2_path, jwt, json=component_data)
        except ToolError as exc:
            raise ToolError(_enrich_graph_update_error(str(exc))) from exc

        return {
            "status": "ok",
            "component": target.get("name", component_instance_id),
            "updated_parameters": sorted(updated_names),
        }
