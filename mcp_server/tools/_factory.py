"""Declarative proxy-tool factory for MCP tools that wrap a single backend API call.

Most MCP tools follow the same pattern: authenticate, optionally resolve org
context or check roles, then forward to a single backend HTTP call.  This
module lets you describe such tools as data (ToolSpec) and registers them on
the FastMCP instance without hand-writing the boilerplate each time.

Custom tools that do validation, multi-step orchestration, or client-side
filtering are still defined as regular ``@mcp.tool()`` functions in their
respective modules.
"""

from __future__ import annotations

from dataclasses import dataclass
from inspect import Parameter, Signature
from typing import Any, Literal
from urllib.parse import quote

from fastmcp import FastMCP

from mcp_server.client import api
from mcp_server.context import require_org_context, require_role
from mcp_server.tools.context_tools import _get_auth


@dataclass(frozen=True)
class Param:
    """One tool parameter exposed to the MCP client."""

    name: str
    annotation: type = str
    default: Any = Parameter.empty
    description: str = ""


@dataclass(frozen=True)
class ToolSpec:
    """Declarative description of a single-call proxy tool.

    Attributes:
        path:           URL template, may contain ``{org_id}`` and path-param
                        placeholders like ``{project_id}``.
        scope:          ``"auth"`` (JWT only), ``"org"`` (require active org),
                        or ``"role"`` (require specific roles).
        body_param:     A single param whose value IS the JSON body (passthrough).
        body_fields:    Multiple params assembled into a JSON body dict
                        (keys = param names).
        body_org_key:   If set, inject ``org_id`` into the JSON body under this key.
        org_query_key:  If set, inject ``org_id`` as this query-string parameter.
    """

    name: str
    description: str
    method: Literal["get", "post", "put", "patch", "delete"]
    path: str
    scope: Literal["auth", "org", "role"] = "auth"
    roles: tuple[str, ...] = ()
    path_params: tuple[Param, ...] = ()
    query_params: tuple[Param, ...] = ()
    body_param: Param | None = None
    body_fields: tuple[Param, ...] = ()
    body_org_key: str | None = None
    org_query_key: str | None = None
    return_annotation: type = dict
    trim: bool = True


def _validate_spec(spec: ToolSpec) -> None:
    """Fail fast on common ToolSpec misconfigurations."""
    import re
    placeholders = set(re.findall(r"\{(\w+)\}", spec.path))
    path_param_names = {p.name for p in spec.path_params}
    auto_resolved = set()
    if "{org_id}" in spec.path:
        auto_resolved.add("org_id")
    unresolved = placeholders - path_param_names - auto_resolved
    if unresolved:
        raise ValueError(
            f"ToolSpec '{spec.name}': path '{spec.path}' has unresolved "
            f"placeholders {unresolved} — add them to path_params or use org_id injection."
        )
    if spec.body_org_key and spec.scope not in ("org", "role"):
        raise ValueError(
            f"ToolSpec '{spec.name}': body_org_key='{spec.body_org_key}' requires "
            f"scope='org' or 'role' (got scope='{spec.scope}')."
        )
    if spec.scope == "role" and not spec.roles:
        raise ValueError(f"ToolSpec '{spec.name}': scope='role' requires a non-empty roles tuple.")


def _build_handler(spec: ToolSpec):
    async def handler(*args: Any, **kwargs: Any) -> Any:
        bound = handler.__signature__.bind(*args, **kwargs)
        bound.apply_defaults()
        resolved = bound.arguments

        jwt, user_id = _get_auth()

        org_id: str | None = None
        if spec.scope == "role":
            org_id = (await require_role(user_id, *spec.roles))["org_id"]
        elif spec.scope == "org":
            org_id = (await require_org_context(user_id))["org_id"]

        path_values = {p.name: quote(str(resolved[p.name]), safe="") for p in spec.path_params}
        if org_id and "{org_id}" in spec.path:
            path_values["org_id"] = org_id
        resolved_path = spec.path.format(**path_values)

        json_body: Any = None
        if spec.body_param:
            json_body = resolved[spec.body_param.name]
        elif spec.body_fields or spec.body_org_key:
            json_body = {bf.name: resolved[bf.name] for bf in spec.body_fields if resolved[bf.name] is not None}
            if spec.body_org_key and org_id:
                json_body[spec.body_org_key] = org_id

        call_kwargs: dict[str, Any] = {}
        if json_body is not None:
            call_kwargs["json"] = json_body
        for qp in spec.query_params:
            val = resolved.get(qp.name)
            if val is not None:
                call_kwargs[qp.name] = val
        if org_id and spec.org_query_key:
            call_kwargs[spec.org_query_key] = org_id

        method_fn = getattr(api, spec.method)
        return await method_fn(resolved_path, jwt, trim=spec.trim, **call_kwargs)

    handler.__name__ = spec.name
    handler.__qualname__ = spec.name

    all_params: list[Param] = list(spec.path_params)
    remaining: list[Param] = list(spec.body_fields)
    if spec.body_param:
        remaining.append(spec.body_param)
    remaining.extend(spec.query_params)
    all_params.extend(p for p in remaining if p.default is Parameter.empty)
    all_params.extend(p for p in remaining if p.default is not Parameter.empty)

    sig_params = []
    for p in all_params:
        kw: dict[str, Any] = {"annotation": p.annotation}
        if p.default is not Parameter.empty:
            kw["default"] = p.default
        sig_params.append(Parameter(p.name, Parameter.POSITIONAL_OR_KEYWORD, **kw))

    handler.__signature__ = Signature(sig_params, return_annotation=spec.return_annotation)
    handler.__annotations__ = {p.name: p.annotation for p in all_params}
    handler.__annotations__["return"] = spec.return_annotation

    doc_lines = [spec.description]
    documented = [p for p in all_params if p.description]
    if documented:
        doc_lines += ["", "Args:"]
        doc_lines += [f"    {p.name}: {p.description}" for p in documented]
    handler.__doc__ = "\n".join(doc_lines)

    return handler


def register_proxy_tools(mcp: FastMCP, specs: list[ToolSpec]) -> None:
    for spec in specs:
        _validate_spec(spec)
        mcp.tool()(_build_handler(spec))
