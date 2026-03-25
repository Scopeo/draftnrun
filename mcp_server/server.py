"""Draft'n Run MCP Server.

Standalone MCP server that wraps the Draft'n Run backend API
and Supabase direct queries behind an authenticated MCP interface.
Auth is delegated to Supabase's OAuth 2.1 Server via FastMCP's SupabaseProvider.
"""

import re
from typing import Any

import sentry_sdk
from fastmcp import FastMCP
from fastmcp.server.auth.providers.supabase import SupabaseProvider
from sentry_sdk.integrations.mcp import MCPIntegration
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from mcp_server.docs import DOMAIN_DESCRIPTIONS
from mcp_server.docs import register as register_docs
from mcp_server.settings import settings
from mcp_server.tools import register_all_tools

INSTRUCTIONS_HEADER = """\
Draft'n Run — no-code AI agent builder (DAGs of components).

CRITICAL: Never invent, guess, or fabricate UUIDs. Every ID you pass to a tool \
MUST come from a previous tool response in this session (list_*, get_*, create_*, search_*). \
If you don't have the ID, call the appropriate discovery tool first. \
Never reuse IDs or graph JSON from another project/org — re-fetch current state with \
get_graph, list_components, search_components, list_sources, etc.

First (sequential, not parallel): list_my_organizations → select_organization → wait for success before other tools.

Domain model:
  Organization
   ├── Agents (type=AGENT) → Graph Runners (draft/prod) → Runs
   ├── Workflows (type=WORKFLOW) → Graph (visual DAG) → Runs
   ├── Variables, Secrets (admin only)
   ├── Knowledge Sources → Documents
   ├── QA Datasets → Judges → Evaluations
   ├── Cron Jobs, OAuth Connections, API Keys
   └── Monitoring (traces, charts, KPIs, credits)

For versioned work, call get_project_overview(project_id) before editing, publishing, or reasoning about live behavior.

For detailed guidance on any domain, fetch the matching docs:// resource \
or call get_guide(domain):
"""

_BEARER_TOKEN_RE = re.compile(r"Bearer\s+[A-Za-z0-9._\-+/=]+", re.IGNORECASE)
_SENSITIVE_FIELD_MARKERS = ("authorization", "token", "secret", "password", "api_key", "cookie", "jwt")
_SENSITIVE_ID_FIELDS = {"user", "user_id", "userid"}


def _scrub_sentry_value(value: Any, key: str | None = None) -> Any:
    key_lower = (key or "").lower().replace("-", "_")
    if key_lower.startswith("x_"):
        key_lower_stripped = key_lower[2:]
    else:
        key_lower_stripped = key_lower
    if (
        key_lower in _SENSITIVE_ID_FIELDS
        or key_lower_stripped in _SENSITIVE_ID_FIELDS
        or any(marker in key_lower for marker in _SENSITIVE_FIELD_MARKERS)
    ):
        return "[REDACTED]"

    if isinstance(value, dict):
        return {item_key: _scrub_sentry_value(item_value, str(item_key)) for item_key, item_value in value.items()}

    if isinstance(value, list):
        return [_scrub_sentry_value(item) for item in value]

    if isinstance(value, str):
        return _BEARER_TOKEN_RE.sub("Bearer [REDACTED]", value)

    return value


def _before_send(event: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any] | None:
    del hint
    return _scrub_sentry_value(event)


def _before_send_log(log: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any] | None:
    del hint
    return _scrub_sentry_value(log)


def _before_send_transaction(event: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any] | None:
    del hint
    return _scrub_sentry_value(event)


def _build_instructions() -> str:
    lines = [INSTRUCTIONS_HEADER]
    for domain, description in DOMAIN_DESCRIPTIONS.items():
        lines.append(f"  docs://{domain:<20s} {description}")
    return "\n".join(lines)


def create_app() -> FastMCP:
    if settings.SENTRY_DSN:
        sentry_sdk.init(
            dsn=settings.SENTRY_DSN,
            environment=settings.SENTRY_ENVIRONMENT,
            send_default_pii=False,
            traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
            enable_logs=False,
            before_send=_before_send,
            before_send_log=_before_send_log,
            before_send_transaction=_before_send_transaction,
            integrations=[MCPIntegration()],
        )

    auth = SupabaseProvider(
        project_url=settings.SUPABASE_PROJECT_URL,
        base_url=settings.MCP_BASE_URL,
    )

    mcp = FastMCP(
        name="Draft'n Run",
        auth=auth,
        instructions=_build_instructions(),
    )

    @mcp.custom_route("/health", methods=["GET"])
    async def health(request: Request) -> Response:
        return JSONResponse({"status": "ok"})

    register_docs(mcp)
    register_all_tools(mcp)

    return mcp


app = create_app()


if __name__ == "__main__":
    app.run(transport="http", host="0.0.0.0", port=8090)
