"""High-level agent configuration tools.

These composite tools handle the read-modify-write cycle and data
transformation that the front-end performs in useUpdateAgentMutation,
so the AI doesn't have to manipulate raw backend payloads.

IMPORTANT: all GET calls that feed a subsequent PUT use ``trim=False``
to preserve the full payload.  Trimming a read-modify-write response
corrupts the write-back (empty model_parameters / tools).
"""

from typing import Optional

from fastmcp import FastMCP

from mcp_server.client import api
from mcp_server.context import require_org_context
from mcp_server.tools._defaults import ensure_provider_model_format
from mcp_server.tools.context_tools import _get_auth

PARAMETER_MAP = {
    "system_prompt": "initial_prompt",
    "model": "completion_model",
    "temperature": "default_temperature",
    "max_tokens": "max_tokens",
}


def _extract_valid_models(existing_params: list[dict]) -> list[dict]:
    """Return the ``options`` list from the ``completion_model`` parameter, if any."""
    completion_param = next((p for p in existing_params if p.get("name") == "completion_model"), None)
    if not completion_param:
        return []
    ui_props = completion_param.get("ui_component_properties") or {}
    return ui_props.get("options") or []


def _validate_model_choice(prefixed_model: str, existing_params: list[dict]) -> None:
    """Raise if *prefixed_model* is not in the agent's available model options."""
    options = _extract_valid_models(existing_params)
    if not options:
        return
    valid_values = {opt["value"] for opt in options if "value" in opt}
    if prefixed_model in valid_values:
        return
    labels = [f"{opt.get('label', '?')} → {opt['value']}" for opt in options if "value" in opt]
    raise ValueError(
        f"Model '{prefixed_model}' is not available on this agent. "
        f"Pick one of:\n  " + "\n  ".join(labels)
    )


def _merge_model_parameters(
    existing_params: list[dict],
    updates: dict,
) -> list[dict]:
    """Merge user-provided updates into the existing model_parameters list."""
    backend_updates = {}
    for ui_key, backend_key in PARAMETER_MAP.items():
        if ui_key in updates and updates[ui_key] is not None:
            value = updates[ui_key]
            if ui_key == "model":
                value = ensure_provider_model_format(str(value))
            backend_updates[backend_key] = value

    merged = []
    for param in existing_params:
        p = {"name": param["name"], "value": param.get("value", param.get("default"))}
        if param["name"] in backend_updates:
            p["value"] = backend_updates[param["name"]]
        merged.append(p)

    return merged


async def _fetch_component_by_name(jwt: str, org_id: str, release_stage: str, component_name: str) -> dict:
    """Lookup a component from the catalog by its display name.

    Matches against both ``name`` and ``component_name`` fields
    (case-insensitive) so callers can pass the value returned by
    ``search_components()``.
    """
    catalog = await api.get(f"/components/{org_id}", jwt, trim=False, release_stage=release_stage)
    components = catalog if isinstance(catalog, list) else catalog.get("components", [])

    target = component_name.lower()
    for comp in components:
        if (comp.get("name") or "").lower() == target or (comp.get("component_name") or "").lower() == target:
            return comp

    available = sorted({c.get("name", c.get("component_name", "?")) for c in components})
    raise ValueError(
        f"Component '{component_name}' not found in the catalog. "
        f"Available components: {', '.join(available[:30])}"
    )


def _validate_agent_tool_component(component: dict, existing_tools: list[dict]) -> None:
    """Reject tool additions that the frontend or backend would not handle safely."""
    component_name = component.get("name") or component.get("component_name") or "unknown"
    component_version_id = component.get("component_version_id") or component.get("id")

    if not component.get("function_callable", False):
        raise ValueError(
            f"Component '{component_name}' is not function_callable and cannot be attached as an agent tool. "
            "Use workflow graph editing for non-tool components."
        )

    if component.get("integration"):
        integration = component["integration"]
        integration_name = integration.get("name") or "unknown"
        integration_service = integration.get("service") or "unknown"
        raise ValueError(
            f"Component '{component_name}' requires integration '{integration_name}:{integration_service}', "
            "but add_tool_to_agent cannot create the required integration relationship. "
            "Configure it in the web UI or use a graph-editing flow that can preserve the integration."
        )

    if any(
        tool.get("component_version_id") == component_version_id
        or tool.get("component_name") == component_name
        or tool.get("name") == component_name
        for tool in existing_tools
    ):
        raise ValueError(
            f"Tool '{component_name}' is already present on this agent. "
            "This MCP helper supports one instance per component, matching the frontend selection UI."
        )


def _build_tool_entry(component: dict, tool_parameters: dict) -> dict:
    """Build a tool entry for the agent from a component definition."""
    params = []
    for param in component.get("parameters", []):
        if param.get("kind") == "input":
            continue
        p = {
            "name": param["name"],
            "type": param.get("type", "string"),
            "nullable": param.get("nullable", False),
            "default": param.get("default"),
            "value": tool_parameters.get(param["name"], param.get("default")),
            "order": param.get("order"),
            "ui_component": param.get("ui_component"),
            "ui_component_properties": param.get("ui_component_properties"),
            "is_advanced": param.get("is_advanced", False),
        }
        params.append(p)

    return {
        "name": component.get("name", component.get("component_name")),
        "component_id": component.get("component_id", component.get("id")),
        "component_version_id": component.get("component_version_id") or component.get("version_id"),
        "component_name": component.get("name", component.get("component_name")),
        "component_description": component.get("description"),
        "parameters": params,
        "tool_description": component.get("tool_description"),
        "is_start_node": False,
    }


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    async def configure_agent(
        agent_id: str,
        graph_runner_id: str,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> dict:
        """Configure an agent's model settings and system prompt.

        Only provided fields are updated — everything else is preserved.
        Handles the model provider prefix automatically (e.g. 'gpt-4.1'
        becomes 'openai:gpt-4.1').

        IMPORTANT — do NOT invent model names.  The model value is validated
        against the options available on this agent.  Use ``get_graph()`` to
        inspect the ``completion_model`` parameter's options list, or omit the
        ``model`` argument to keep the current model.

        Args:
            agent_id: The agent (project) ID.
            graph_runner_id: The graph runner version ID.
            system_prompt: The agent's instructions / system prompt.
            model: LLM model identifier exactly as listed in the agent's
                completion_model options (e.g. 'gpt-4.1',
                'anthropic:claude-sonnet-4-5').  Raises ValueError if the
                model is not in the available options.
            temperature: Sampling temperature (0.0 - 2.0).
            max_tokens: Maximum response tokens.
            name: Update the agent's display name.
            description: Update the agent's description.
        """
        jwt, _ = _get_auth()
        current = await api.get(f"/agents/{agent_id}/versions/{graph_runner_id}", jwt, trim=False)

        updates = {
            "system_prompt": system_prompt,
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        existing_params = current.get("model_parameters", [])
        available_param_names = {param["name"] for param in existing_params}

        if model is not None:
            _validate_model_choice(ensure_provider_model_format(str(model)), existing_params)

        merged_params = _merge_model_parameters(existing_params, updates)

        initial_prompt_param = next((p for p in merged_params if p["name"] == "initial_prompt"), None)
        final_prompt = (
            initial_prompt_param["value"]
            if initial_prompt_param
            else (system_prompt or "")
        )

        update_data = {
            "name": name if name is not None else current.get("name", ""),
            "description": description if description is not None else current.get("description", ""),
            "system_prompt": final_prompt,
            "model_parameters": merged_params,
            "tools": current.get("tools", []),
        }

        await api.put(f"/agents/{agent_id}/versions/{graph_runner_id}", jwt, json=update_data)

        applied = {k: v for k, v in updates.items() if v is not None}
        if name is not None:
            applied["name"] = name
        if description is not None:
            applied["description"] = description

        warnings = []
        for ui_key, backend_key in PARAMETER_MAP.items():
            if ui_key == "system_prompt":
                continue
            if updates.get(ui_key) is not None and backend_key not in available_param_names:
                warnings.append(
                    f"Ignored '{ui_key}': the current agent version does not expose backend parameter '{backend_key}'."
                )

        return {
            "status": "ok",
            "agent_id": agent_id,
            "applied": applied,
            "warnings": warnings,
            "hint": "Test with run_agent, or add tools with add_tool_to_agent.",
        }

    @mcp.tool()
    async def add_tool_to_agent(
        agent_id: str,
        graph_runner_id: str,
        component_name: str,
        tool_parameters: Optional[dict] = None,
    ) -> dict:
        """Add a tool to an agent by component name.

        Looks up the component in the catalog, builds the tool entry with
        default parameters (overridden by tool_parameters), and appends it.

        IMPORTANT — pass the **display name** returned by
        ``search_components()``, e.g. ``"Internet Search (Linkup)"``,
        ``"Internet Search (OpenAI)"``.  Matching is case-insensitive.

        Safety constraints:
        - only `function_callable` catalog entries are valid agent tools
        - this helper is one-tool-per-component, matching the frontend UI
        - integration-backed tools are rejected because this helper cannot wire
          the required integration relationship automatically

        Args:
            agent_id: The agent (project) ID.
            graph_runner_id: The graph runner version ID.
            component_name: Component display name from search_components()
                (e.g. 'Internet Search (Linkup)', 'Internet Search (OpenAI)').
            tool_parameters: Optional overrides for tool parameters
                (e.g. {"timeout": 30}). Defaults are used for unspecified params.
        """
        if tool_parameters is None:
            tool_parameters = {}

        jwt, user_id = _get_auth()
        org = await require_org_context(user_id)
        release_stage = org.get("release_stage") or "public"

        component = await _fetch_component_by_name(jwt, org["org_id"], release_stage, component_name)
        current = await api.get(f"/agents/{agent_id}/versions/{graph_runner_id}", jwt, trim=False)

        existing_tools = current.get("tools", [])
        _validate_agent_tool_component(component, existing_tools)
        new_tool = _build_tool_entry(component, tool_parameters)
        existing_tools.append(new_tool)

        update_data = {
            "name": current.get("name", ""),
            "description": current.get("description", ""),
            "system_prompt": current.get("system_prompt", ""),
            "model_parameters": current.get("model_parameters", []),
            "tools": existing_tools,
        }

        await api.put(f"/agents/{agent_id}/versions/{graph_runner_id}", jwt, json=update_data)
        return {
            "status": "ok",
            "added_tool": component_name,
            "total_tools": len(existing_tools),
        }

    @mcp.tool()
    async def remove_tool_from_agent(
        agent_id: str,
        graph_runner_id: str,
        component_name: str,
    ) -> dict:
        """Remove a tool from an agent by component name.

        Args:
            agent_id: The agent (project) ID.
            graph_runner_id: The graph runner version ID.
            component_name: Name of the component to remove.
        """
        jwt, _ = _get_auth()
        current = await api.get(f"/agents/{agent_id}/versions/{graph_runner_id}", jwt, trim=False)

        existing_tools = current.get("tools", [])
        target = component_name.lower()
        filtered = [
            t for t in existing_tools
            if (t.get("component_name") or "").lower() != target
            and (t.get("name") or "").lower() != target
        ]
        if len(filtered) == len(existing_tools):
            tool_names = [t.get("component_name") or t.get("name") for t in existing_tools]
            raise ValueError(
                f"Tool '{component_name}' not found on this agent. "
                f"Current tools: {tool_names}"
            )

        update_data = {
            "name": current.get("name", ""),
            "description": current.get("description", ""),
            "system_prompt": current.get("system_prompt", ""),
            "model_parameters": current.get("model_parameters", []),
            "tools": filtered,
        }

        await api.put(f"/agents/{agent_id}/versions/{graph_runner_id}", jwt, json=update_data)
        return {
            "status": "ok",
            "removed_tool": component_name,
            "remaining_tools": len(filtered),
        }
