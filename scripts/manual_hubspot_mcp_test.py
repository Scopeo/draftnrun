"""
Manual sanity script for HubSpotMCPTool.

What it does:
- Connects to HubSpot's MCP server (https://mcp.hubspot.com/) using OAuth Bearer token.
- Auto-discovers available tools and prints their names/descriptions (first 10).
- Optionally executes a single tool with JSON args and prints the raw output.

Usage (hits the live HubSpot MCP server; requires HUBSPOT_MCP_ACCESS_TOKEN):
    uv run python scripts/manual_hubspot_mcp_test.py

Optional: call a specific tool
    uv run python scripts/manual_hubspot_mcp_test.py \
        --call-tool get_user_details \
        --tool-args '{}'

Note: This is a dev helper for quick manual verification; no production dependency.
"""

import argparse
import asyncio
import json

from engine.components.tools.hubspot_mcp_tool import HubSpotMCPTool, HubSpotMCPToolInputs
from engine.components.types import ComponentAttributes
from engine.trace.trace_manager import TraceManager


async def main():
    parser = argparse.ArgumentParser(description="Test HubSpot MCP Tool connection")
    parser.add_argument(
        "--call-tool",
        help="Optional: tool name to invoke once (e.g., get_user_details)",
    )
    parser.add_argument(
        "--tool-args",
        help="Optional: JSON string of arguments to send with --call-tool",
    )
    args = parser.parse_args()

    trace_manager = TraceManager(project_name="manual-hubspot-mcp-test")
    component_attributes = ComponentAttributes(component_instance_name="manual-hubspot-mcp-tool")

    print("Connecting to HubSpot MCP server...")
    tool = await HubSpotMCPTool.from_mcp_server(
        trace_manager=trace_manager,
        component_attributes=component_attributes,
    )

    descriptions = tool.get_tool_descriptions()
    print(f"\n✅ Fetched {len(descriptions)} tool descriptions from HubSpot MCP server")
    print("\nAvailable tools:")
    for td in descriptions[:10]:
        print(f"  - {td.name}: {td.description}")
    if len(descriptions) > 10:
        print(f"  ... and {len(descriptions) - 10} more")

    if args.call_tool:
        tool_args = json.loads(args.tool_args) if args.tool_args else {}
        inputs = HubSpotMCPToolInputs(tool_name=args.call_tool, tool_arguments=tool_args)
        print(f"\n🔧 Calling tool '{args.call_tool}' with args: {tool_args}")
        result = await tool._run_without_io_trace(inputs=inputs, ctx={})
        print(f"\n✅ Tool '{args.call_tool}' response:")
        print(f"   Output: {result.output}")
        if result.is_error:
            print("   ⚠️  Server marked this as an error")
    else:
        print("\n💡 Tip: Use --call-tool <tool_name> to test a specific tool")
        print("   Example: --call-tool get_user_details --tool-args '{}'")


if __name__ == "__main__":
    asyncio.run(main())
