"""Run management tools.

The MCP execution surface currently exposes only `messages` for async runs.
It does not expose arbitrary Start payload fields or file download helpers.
"""

import asyncio
import time

from fastmcp import FastMCP

from mcp_server.client import api
from mcp_server.tools._factory import Param, ToolSpec, register_proxy_tools
from mcp_server.tools.context_tools import _get_auth

DEFAULT_POLL_INTERVAL = 2
MAX_POLL_INTERVAL = 10

_P_PROJECT = Param("project_id", str, description="The project ID.")
_P_RUN = Param("run_id", str, description="The run ID.")

PROXY_SPECS: list[ToolSpec] = [
    ToolSpec(
        name="get_run",
        description=(
            "Get details of a specific run.\n\n"
            "Use this after `run_agent` timeouts or when you need to inspect status "
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
    async def list_runs(project_id: str, page: int = 1, page_size: int = 50) -> dict:
        """List runs for a project with pagination.

        Args:
            project_id: The project ID.
            page: Page number (1-based). Defaults to 1.
            page_size: Results per page (max 100). Defaults to 50.
        """
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
    async def run_agent(
        project_id: str,
        graph_runner_id: str,
        messages: list[dict],
        timeout: int = 60,
    ) -> dict:
        """Run an agent with messages and wait for the result.

        Sends only the `messages` payload, then polls for completion up to
        `timeout` seconds. Returns the final result directly — no need to
        manually poll. This wrapper does not expose arbitrary Start-node fields
        or a file download helper.

        Safety reminders:
        - Choose the `graph_runner_id` deliberately. Draft is for iterative
          testing; production is for live-behavior checks.
        - The backend can use `conversation_id`, `set_id`, and extra Start
          payload fields, but this MCP wrapper does not expose them.
        - If the run times out here, continue with `get_run` and
          `get_run_result` rather than assuming failure.

        Args:
            project_id: The project ID.
            graph_runner_id: The graph runner version ID.
            messages: List of message objects (e.g. [{"role": "user", "content": "Hello"}]).
            timeout: Max seconds to wait for completion. Defaults to 60.
        """
        if not isinstance(timeout, int) or timeout <= 0:
            raise ValueError("timeout must be a positive integer")

        jwt, _ = _get_auth()
        response = await api.post(
            f"/projects/{project_id}/graphs/{graph_runner_id}/chat/async",
            jwt,
            json={"messages": messages},
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
