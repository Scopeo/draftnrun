"""Run management tools.

The `run` tool sends a full payload dict to the backend's async endpoint and
polls for the result.  It does not expose file download helpers.
"""

import asyncio
import logging
import time
from typing import Annotated, Optional
from uuid import UUID

import httpx
from fastmcp import FastMCP
from pydantic import Field

from mcp_server.client import api
from mcp_server.context import require_org_context
from mcp_server.tools._factory import Param, ToolSpec, register_proxy_tools
from mcp_server.tools.context_tools import _get_auth

logger = logging.getLogger(__name__)

DEFAULT_POLL_INTERVAL = 2
MAX_POLL_INTERVAL = 10

_P_PROJECT = Param("project_id", UUID, description="The project ID (from list_projects or get_project_overview).")
_P_RUN = Param("run_id", UUID, description="The run ID (from list_runs or run).")

PROXY_SPECS: list[ToolSpec] = [
    ToolSpec(
        name="get_run",
        description=(
            "Get details of a specific run.\n\n"
            "Use this after `run` timeouts or when you need to inspect status "
            "transitions before fetching the final result.\n\n"
            "Note: does not include the original input payload. To retrieve input, "
            "extract `trace_id` from the response and call `get_trace_tree(trace_id)`."
        ),
        method="get",
        path="/projects/{project_id}/runs/{run_id}",
        path_params=(_P_PROJECT, _P_RUN),
    ),
    ToolSpec(
        name="get_run_result",
        description=(
            "Get the output result of a completed run.\n\n"
            "Returns output only — not the original input. For input data, use "
            "`get_trace_tree` with the run's `trace_id`.\n\n"
            "Large results may be trimmed to `_truncated` / `partial_data`. Generated "
            "files, when present, are typically surfaced as `files[].s3_key` for this "
            "MCP surface."
        ),
        method="get",
        path="/projects/{project_id}/runs/{run_id}/result",
        path_params=(_P_PROJECT, _P_RUN),
    ),
]


def register(mcp: FastMCP) -> None:
    register_proxy_tools(mcp, PROXY_SPECS)

    @mcp.tool()
    async def list_runs(
        project_id: Annotated[
            Optional[UUID],
            Field(description="Filter by project ID. If omitted, returns runs across all projects in the org."),
        ] = None,
        status: Annotated[
            Optional[str],
            Field(description="Filter by status: 'pending', 'running', 'completed', or 'failed'."),
        ] = None,
        trigger: Annotated[
            Optional[str],
            Field(
                description=(
                    "Filter by trigger type: 'api', 'sandbox', 'webhook', 'cron', or 'qa'. "
                    "Comma-separated for multiple."
                )
            ),
        ] = None,
        env: Annotated[
            Optional[str],
            Field(description="Filter by environment: 'draft' or 'production'. Comma-separated for multiple."),
        ] = None,
        date_from: Annotated[
            Optional[str],
            Field(description="Start of date range filter (ISO 8601, e.g. '2025-06-01T00:00:00Z')."),
        ] = None,
        date_to: Annotated[
            Optional[str],
            Field(description="End of date range filter (ISO 8601, e.g. '2025-06-30T23:59:59Z')."),
        ] = None,
        page: Annotated[int, Field(description="Page number (1-based).")] = 1,
        page_size: Annotated[int, Field(description="Results per page (max 100).")] = 50,
    ) -> dict:
        """List runs for the active organization with optional filters.

        Returns runs across all projects in the org. Each run includes
        project_name, attempt_count, and input_available (whether retry is possible).
        """
        if page < 1:
            raise ValueError("Page must be >= 1 (1-indexed). Pass page=1 for the first page.")
        if page_size < 1:
            raise ValueError("Page size must be >= 1. Recommended range: 10-50.")

        jwt, user_id = _get_auth()
        org = await require_org_context(user_id)
        params: dict = {"page": page, "page_size": min(page_size, 100)}
        if project_id is not None:
            params["project_ids"] = str(project_id)
        if status is not None:
            params["statuses"] = status
        if trigger is not None:
            params["triggers"] = [t for t in (t.strip() for t in trigger.split(",")) if t]
        if env is not None:
            params["envs"] = [e for e in (e.strip() for e in env.split(",")) if e]
        if date_from is not None:
            params["date_from"] = date_from
        if date_to is not None:
            params["date_to"] = date_to
        return await api.get(f"/org/{org['org_id']}/runs", jwt, **params)

    @mcp.tool()
    async def retry_run(
        project_id: Annotated[
            UUID,
            Field(description="The project ID (from list_projects or get_project_overview)."),
        ],
        run_id: Annotated[
            UUID,
            Field(description="The run ID to retry (from list_runs or get_run)."),
        ],
        env: Annotated[
            Optional[str],
            Field(description="Execution env for retry. Typically 'draft' or 'production'."),
        ] = None,
        graph_runner_id: Annotated[
            Optional[UUID],
            Field(description="Optional explicit graph runner to execute the retry against."),
        ] = None,
    ) -> dict:
        """Retry a specific run using persisted input payload.

        The backend creates a new run attempt in the same retry group and enqueues
        it asynchronously. Provide either `env` or `graph_runner_id`.
        """
        if env is None and graph_runner_id is None:
            raise ValueError("Either env or graph_runner_id must be provided")

        jwt, _ = _get_auth()
        body: dict = {}
        if env is not None:
            body["env"] = env
        if graph_runner_id is not None:
            body["graph_runner_id"] = str(graph_runner_id)

        return await api.post(
            f"/projects/{project_id}/runs/{run_id}/retry",
            jwt,
            json=body,
        )

    @mcp.tool()
    async def run(
        project_id: Annotated[
            UUID,
            Field(description="The project ID (from list_projects or get_project_overview)."),
        ],
        graph_runner_id: Annotated[
            UUID,
            Field(description="The graph runner version ID (from get_project_overview)."),
        ],
        payload: Annotated[
            dict,
            Field(
                description=('Request body dict — must contain "messages", may contain additional Start-node fields.'),
            ),
        ],
        timeout: Annotated[int, Field(description="Max seconds to wait for completion.")] = 60,
    ) -> dict:
        """Run an agent or workflow and wait for the result.

        `payload` is the full request body sent to the backend.  It must
        contain a `messages` key and may include any additional Start-node
        fields defined in the graph's `payload_schema`.

        Example — agent (messages only):
            payload={"messages": [{"role": "user", "content": "Hello"}]}

        Example — workflow with custom Start fields:
            payload={"messages": [{"role": "user", "content": "Hello"}],
                     "name": "Ada", "language": "fr"}

        The backend extracts `messages` for the execution pipeline and injects
        remaining keys into `ctx` as Start-node output ports.

        Safety reminders:
        - Choose the `graph_runner_id` deliberately.  Draft is for iterative
          testing; production is for live-behavior checks.
        - If the run times out here, continue with `get_run` and
          `get_run_result` rather than assuming failure.
        """
        if not isinstance(timeout, int) or timeout <= 0:
            raise ValueError("timeout must be a positive integer (seconds). Default is typically 60.")
        if "messages" not in payload:
            raise ValueError(
                "payload must contain a 'messages' key. "
                'Example: {"messages": [{"role": "user", "content": "Hello"}]}'
            )

        jwt, _ = _get_auth()
        response = await api.post(
            f"/projects/{project_id}/graphs/{graph_runner_id}/chat/async",
            jwt,
            json=payload,
        )

        if "message" in response and "run_id" not in response:
            return response

        run_id = response.get("run_id")
        if not run_id:
            return response

        start = time.monotonic()
        interval = DEFAULT_POLL_INTERVAL
        while True:
            remaining = timeout - (time.monotonic() - start)
            if remaining <= 0:
                break

            await asyncio.sleep(min(interval, remaining))

            try:
                run_status = await api.get(f"/projects/{project_id}/runs/{run_id}", jwt)
            except httpx.HTTPError as exc:
                logger.warning("Transient error polling run %s: %s", run_id, exc)
                interval = min(interval + 1, MAX_POLL_INTERVAL)
                continue

            status = run_status.get("status", "")

            if status == "completed":
                try:
                    return await api.get(f"/projects/{project_id}/runs/{run_id}/result", jwt)
                except httpx.HTTPError:
                    return {
                        "status": "completed",
                        "run_id": run_id,
                        "hint": (
                            f"Run completed but result fetch failed. Use get_run_result('{project_id}', '{run_id}')."
                        ),
                    }
            if status == "failed":
                return {
                    "status": "failed",
                    "run_id": run_id,
                    "error": run_status.get("error", "Run failed without details."),
                }

            interval = min(interval + 1, MAX_POLL_INTERVAL)

        elapsed = time.monotonic() - start
        return {
            "status": "timeout",
            "run_id": run_id,
            "elapsed_seconds": round(elapsed, 1),
            "hint": f"Still running. Poll with get_run('{project_id}', '{run_id}').",
        }
