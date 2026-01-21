"""LocalMCPTool stdio smoke test / dev runner.

This script is meant to validate that `LocalMCPTool` can:
- spawn a stdio MCP server as a subprocess
- auto-discover tools (list_tools)
- call tools over a *persistent* stdio session (state shared across calls)

It also works as a handy runner for any MCP server that supports stdio, e.g.:
    github-mcp-server stdio

Examples:
    # Default (FastMCP debug server bundled in this repo)
    uv run python scripts/mcp/test_local_mcp_tool.py --preset fastmcp

    # GitHub MCP server (requires env var)
    export GITHUB_PERSONAL_ACCESS_TOKEN="..."
    uv run python scripts/mcp/test_local_mcp_tool.py --preset github

    # Call a specific tool once (JSON args)
    uv run python scripts/mcp/test_local_mcp_tool.py --preset fastmcp --call list_items --tool-args '{}'
"""

import asyncio
import json
import os
from argparse import ArgumentParser
from pathlib import Path

from engine.components.tools.mcp.local_mcp_tool import LocalMCPTool
from engine.components.tools.mcp.shared import MCPToolInputs
from engine.components.types import ComponentAttributes


def _parse_key_value_pairs(pairs: list[str] | None) -> dict[str, str]:
    if not pairs:
        return {}
    env: dict[str, str] = {}
    for pair in pairs:
        if "=" not in pair:
            raise ValueError(f"Invalid --env entry '{pair}'. Expected KEY=VALUE.")
        key, value = pair.split("=", 1)
        env[key] = value
    return env


def _preset_command_args(preset: str, github_toolsets: str | None) -> tuple[str, list[str]]:
    if preset == "fastmcp":
        return "uv", ["run", "python", "scripts/mcp/fastmcp_debug_server.py"]
    if preset == "github":
        args = ["stdio", "--read-only"]
        if github_toolsets:
            args.extend(["--toolsets", github_toolsets])
        return "github-mcp-server", args
    raise ValueError(f"Unknown preset '{preset}'.")


async def main():
    parser = ArgumentParser(description="LocalMCPTool stdio smoke test / dev runner.")
    parser.add_argument(
        "--preset",
        choices=["fastmcp", "github"],
        default="fastmcp",
        help="Command preset to run a known stdio MCP server.",
    )
    parser.add_argument("--command", help="Override: stdio server command to execute.")
    parser.add_argument(
        "--args",
        nargs="*",
        default=None,
        help="Override: stdio server args (space-separated). If omitted, uses the selected preset.",
    )
    parser.add_argument(
        "--cwd",
        help="Working directory for the subprocess (defaults to current directory).",
    )
    parser.add_argument(
        "--env",
        action="append",
        default=[],
        help="Extra env var to set for the subprocess (repeatable), format KEY=VALUE.",
    )
    parser.add_argument(
        "--max-tools",
        type=int,
        default=30,
        help="Max number of tools to print.",
    )
    parser.add_argument(
        "--call",
        help="Optional: tool name to invoke once after discovery.",
    )
    parser.add_argument(
        "--tool-args",
        default="{}",
        help="Optional: JSON string of arguments to send with --call.",
    )
    parser.add_argument(
        "--demo-fastmcp-state",
        action="store_true",
        help="Only for --preset fastmcp: run list/write/read/list to demonstrate state sharing.",
    )

    # GitHub preset helpers
    parser.add_argument(
        "--github-token-env",
        default="GITHUB_PERSONAL_ACCESS_TOKEN",
        help="Env var name that contains the GitHub token (only used for --preset github).",
    )
    parser.add_argument(
        "--github-toolsets",
        help="Comma-separated GitHub toolsets to enable (only used for --preset github).",
    )

    args = parser.parse_args()

    command, command_args = _preset_command_args(args.preset, github_toolsets=args.github_toolsets)
    if args.command:
        command = args.command
    if args.args is not None:
        command_args = args.args

    env_overrides = _parse_key_value_pairs(args.env)
    env = os.environ.copy()
    env.update(env_overrides)

    if args.preset == "github" and args.github_token_env:
        token = os.environ.get(args.github_token_env)
        if token:
            env[args.github_token_env] = token
        else:
            print(f"Warning: env var '{args.github_token_env}' is not set. GitHub tools may fail.")

    cwd = Path(args.cwd) if args.cwd else None

    trace_manager = object()
    component_attributes = ComponentAttributes(component_instance_name="local-mcp-test")

    async with await LocalMCPTool.from_mcp_server(
        trace_manager=trace_manager,
        component_attributes=component_attributes,
        command=command,
        args=command_args,
        env=env,
        cwd=cwd,
    ) as tool:
        descriptions = tool.get_tool_descriptions()
        print(f"Server: {command} {' '.join(command_args)}")
        print(f"Discovered {len(descriptions)} tools")
        for td in descriptions[: max(args.max_tools, 0)]:
            print(f"- {td.name}: {td.description}")
        if args.max_tools and len(descriptions) > args.max_tools:
            print(f"... and {len(descriptions) - args.max_tools} more")

        async def call_tool(tool_name: str, tool_args: dict) -> None:
            inputs = MCPToolInputs(tool_name=tool_name, tool_arguments=tool_args)
            result = await tool._run_without_io_trace(inputs=inputs, ctx={})
            print(f"\nTool '{tool_name}' response:\n{result.output}")

        if args.demo_fastmcp_state and args.preset == "fastmcp":
            await call_tool("list_items", {})
            await call_tool("write_item", {"key": "test", "value": "works!"})
            await call_tool("read_item", {"key": "test"})
            await call_tool("list_items", {})
            return

        if not args.call:
            return

        try:
            tool_args = json.loads(args.tool_args) if args.tool_args else {}
        except json.JSONDecodeError as exc:
            raise SystemExit(f"Invalid --tool-args JSON: {exc}") from exc

        await call_tool(args.call, tool_args)


if __name__ == "__main__":
    asyncio.run(main())
