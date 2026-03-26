"""Run management tools.

The `run` tool sends a full payload dict to the backend's async endpoint and
polls for the result.  It does not expose file download helpers.
"""

import asyncio
import time
from typing import Annotated
from uuid import UUID

from fastmcp import FastMCP
from pydantic import Field

from mcp_server.client import api
from mcp_server.tools._factory import Param, ToolSpec, register_proxy_tools
from mcp_server.tools.context_tools import _get_auth

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
            "transitions before fetching the final result."
        ),
        method="get",
        path="/projects/{project_id}/runs/{run_id}",
        path_params=(_P_PROJECT, _P_RUN),
    ),
    ToolSpec(
        name="get_run_result",
        description=(
            "Get the output result of a completed run.\n\n"
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
        project_id: Annotated[UUID, Field(description="The project ID (from list_projects or get_project_overview).")],
        page: Annotated[int, Field(description="Page number (1-based).")] = 1,
        page_size: Annotated[int, Field(description="Results per page (max 100).")] = 50,
    ) -> dict:
        """List runs for a project with pagination."""
        if page < 1:
            raise ValueError("Page must be greater than or equal to 1.")
        if page_size < 1:
            raise ValueError("Page size must be greater than or equal to 1.")

        jwt, _ = _get_auth()
        return await api.get(
            f"/projects/{project_id}/runs",
            jwt,
            page=page,
            page_size=min(page_size, 100),
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
                description=(
                    'Request body dict — must contain "messages", may contain additional '
                    "Start-node fields."
                ),
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
            raise ValueError("timeout must be a positive integer")
        if "messages" not in payload:
            raise ValueError("payload must contain a 'messages' key")

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

            run_status = await api.get(f"/projects/{project_id}/runs/{run_id}", jwt)
            status = run_status.get("status", "")

            if status == "completed":
                return await api.get(f"/projects/{project_id}/runs/{run_id}/result", jwt)
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
