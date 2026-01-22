"""
Manual sanity script for RemoteMCPTool.

What it does:
- Connects to the given MCP server using the specified transport (SSE or Streamable HTTP).
- Auto-discovers available tools and prints their names/descriptions (first 10).
- Optionally executes a single tool with JSON args and prints the raw output.

Usage with presets (recommended):
    # Linear (SSE transport)
    uv run python scripts/mcp/manual_remote_mcp_test.py --preset linear

    # HubSpot (Streamable HTTP transport)
    uv run python scripts/mcp/manual_remote_mcp_test.py --preset hubspot

    # Rube (Streamable HTTP transport)
    uv run python scripts/mcp/manual_remote_mcp_test.py --preset rube

Manual usage (custom servers):
    uv run python scripts/mcp/manual_remote_mcp_test.py \
        --server-url https://custom.mcp.server/endpoint \
        --api-key "$API_KEY" \
        --transport streamable_http

Optional: call a specific tool
    uv run python scripts/mcp/manual_remote_mcp_test.py --preset linear \
        --call-tool some_tool_name \
        --tool-args '{"key": "value"}'

Note: This is a dev helper for quick manual verification; no production dependency.
"""

import argparse
import asyncio
import json
import os
from typing import Any, Dict

from engine.components.tools.mcp.remote_mcp_tool import MCPTransport, RemoteMCPTool
from engine.components.tools.mcp.shared import MCPToolInputs
from engine.components.types import ComponentAttributes
from engine.trace.trace_manager import TraceManager

PRESETS = {
    "linear": {
        "server_url": "https://mcp.linear.app/sse",
        "transport": MCPTransport.SSE,
        "api_key_env": "LINEAR_API_KEY",
        "bearer_prefix": True,
    },
    "hubspot": {
        "server_url": "https://mcp.hubspot.com/",
        "transport": MCPTransport.STREAMABLE_HTTP,
        "api_key_env": "HUBSPOT_MCP_ACCESS_TOKEN",
        "bearer_prefix": True,
    },
    "rube": {
        "server_url": "https://rube.app/mcp",
        "transport": MCPTransport.STREAMABLE_HTTP,
        "api_key_env": "RUBE_API_KEY",
        "bearer_prefix": True,
    },
}


def build_headers(api_key: str | None, headers_json: str | None, use_bearer: bool) -> Dict[str, Any]:
    headers: Dict[str, Any] = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}" if use_bearer else api_key
    if headers_json:
        headers.update(json.loads(headers_json))
    return headers


async def main():
    parser = argparse.ArgumentParser(description="Manual RemoteMCPTool sanity check.")
    parser.add_argument(
        "--preset",
        choices=list(PRESETS.keys()),
        help="Use a preset configuration (linear, hubspot, rube). Overrides manual flags.",
    )
    parser.add_argument("--server-url", help="MCP server URL (e.g., https://mcp.linear.app/sse)")
    parser.add_argument("--api-key", help="API key for Authorization header.")
    parser.add_argument("--headers-json", help='Extra headers as JSON string, e.g. \'{"X-Test": "1"}\'')
    parser.add_argument(
        "--use-bearer",
        action="store_true",
        help="Prefix the API key with 'Bearer ' in the Authorization header.",
    )
    parser.add_argument(
        "--transport",
        choices=["sse", "streamable_http"],
        default=MCPTransport.SSE.value,
        help="Transport protocol to use (default: sse).",
    )
    parser.add_argument("--call-tool", help="Optional: tool name to invoke once.")
    parser.add_argument("--tool-args", help="Optional: JSON string of arguments to send with --call-tool.")
    args = parser.parse_args()

    # Use preset or manual configuration
    if args.preset:
        preset = PRESETS[args.preset]
        server_url = preset["server_url"]
        transport = preset["transport"]
        api_key = os.getenv(preset["api_key_env"])
        if not api_key:
            raise ValueError(f"Environment variable {preset['api_key_env']} is required for preset '{args.preset}'")
        use_bearer = preset["bearer_prefix"]
        headers = build_headers(api_key, args.headers_json, use_bearer=use_bearer)
        print(f"Using preset: {args.preset}")
    else:
        if not args.server_url:
            raise ValueError("--server-url is required when not using a preset")
        server_url = args.server_url
        transport = MCPTransport(args.transport)
        headers = build_headers(args.api_key, args.headers_json, use_bearer=args.use_bearer)

    trace_manager = TraceManager(project_name="manual-remote-mcp-test")
    component_attributes = ComponentAttributes(component_instance_name="manual-remote-mcp-tool")

    print(f"Connecting to {server_url} using {transport.value} transport...")
    tool = await RemoteMCPTool.from_mcp_server(
        trace_manager=trace_manager,
        component_attributes=component_attributes,
        server_url=server_url,
        headers=headers,
        transport=transport,
    )

    descriptions = tool.get_tool_descriptions()
    print(f"Fetched {len(descriptions)} tool descriptions from {server_url}")
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
