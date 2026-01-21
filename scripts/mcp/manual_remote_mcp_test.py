"""
Manual sanity script for RemoteMCPTool.

What it does:
- Connects to the given MCP server (SSE transport) using the provided headers.
- Auto-discovers available tools and prints their names/descriptions (first 10).
- Optionally executes a single tool with JSON args and prints the raw output.

Usage (hits the live MCP server; requires network/auth):
    uv run python scripts/mcp/manual_remote_mcp_test.py \
        --server-url https://mcp.linear.app/sse \
        --api-key "$LINEAR_API_KEY"  # or use --headers-json for custom headers

Optional: call a specific tool
    uv run python scripts/mcp/manual_remote_mcp_test.py \
        --server-url https://mcp.linear.app/sse \
        --api-key "$LINEAR_API_KEY" \
        --call-tool some_tool_name \
        --tool-args '{"key": "value"}'

Note: This is a dev helper for quick manual verification; no production dependency.
"""

import argparse
import asyncio
import json
from typing import Any, Dict

from engine.components.tools.mcp.remote_mcp_tool import RemoteMCPTool
from engine.components.tools.mcp.shared import MCPToolInputs
from engine.components.types import ComponentAttributes
from engine.trace.trace_manager import TraceManager


def build_headers(api_key: str | None, headers_json: str | None, use_bearer: bool) -> Dict[str, Any]:
    headers: Dict[str, Any] = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}" if use_bearer else api_key
    if headers_json:
        headers.update(json.loads(headers_json))
    return headers


async def main():
    parser = argparse.ArgumentParser(description="Manual RemoteMCPTool sanity check.")
    parser.add_argument("--server-url", required=True, help="MCP server URL (e.g., https://mcp.linear.app/sse)")
    parser.add_argument("--api-key", help="API key for Authorization header (Bearer).")
    parser.add_argument("--headers-json", help='Extra headers as JSON string, e.g. \'{"X-Test": "1"}\'')
    parser.add_argument(
        "--use-bearer",
        action="store_true",
        help="Prefix the API key with 'Bearer ' in the Authorization header (Linear expects raw token by default).",
    )
    parser.add_argument("--call-tool", help="Optional: tool name to invoke once.")
    parser.add_argument("--tool-args", help="Optional: JSON string of arguments to send with --call-tool.")
    args = parser.parse_args()

    headers = build_headers(args.api_key, args.headers_json, use_bearer=args.use_bearer)
    trace_manager = TraceManager(project_name="manual-remote-mcp-test")
    component_attributes = ComponentAttributes(component_instance_name="manual-remote-mcp-tool")

    tool = await RemoteMCPTool.from_mcp_server(
        trace_manager=trace_manager,
        component_attributes=component_attributes,
        server_url=args.server_url,
        headers=headers,
    )

    descriptions = tool.get_tool_descriptions()
    print(f"Fetched {len(descriptions)} tool descriptions from {args.server_url}")
    for td in descriptions[:10]:
        print(f"- {td.name}: {td.description}")
    if len(descriptions) > 10:
        print(f"... and {len(descriptions) - 10} more")

    if args.call_tool:
        tool_args = json.loads(args.tool_args) if args.tool_args else {}
        inputs = MCPToolInputs(tool_name=args.call_tool, tool_arguments=tool_args)
        result = await tool._run_without_io_trace(inputs=inputs, ctx={})
        print(f"\nTool '{args.call_tool}' response:\n{result.output}")


if __name__ == "__main__":
    asyncio.run(main())
