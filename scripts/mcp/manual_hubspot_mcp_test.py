"""
Manual sanity script for HubSpotMCPTool.

What it does:
- Spawns shinzo-labs/hubspot-mcp via npx with OAuth access token.
- Auto-discovers available tools and prints their names/descriptions (first 10).
- Optionally executes a single tool with JSON args and prints the raw output.

Usage (requires HUBSPOT_ACCESS_TOKEN env or --access-token):
    uv run python scripts/mcp/manual_hubspot_mcp_test.py

Optional: call a specific tool
    uv run python scripts/mcp/manual_hubspot_mcp_test.py \
        --call-tool crm_get_contact \
        --tool-args '{"objectId": "123"}'

Note: This is a dev helper for quick manual verification; no production dependency.
"""

import argparse
import asyncio
import json
import os

from engine.components.tools.hubspot_mcp_tool import HubSpotMCPTool
from engine.components.tools.mcp.shared import MCPToolInputs
from engine.components.types import ComponentAttributes
from engine.trace.trace_manager import TraceManager


async def main():
    parser = argparse.ArgumentParser(description="Test HubSpot MCP Tool connection")
    parser.add_argument(
        "--access-token",
        help="HubSpot access token (default: HUBSPOT_ACCESS_TOKEN or HUBSPOT_MCP_ACCESS_TOKEN env)",
    )
    parser.add_argument(
        "--call-tool",
        help="Optional: tool name to invoke once (e.g., crm_get_contact)",
    )
    parser.add_argument(
        "--tool-args",
        help="Optional: JSON string of arguments to send with --call-tool",
    )
    args = parser.parse_args()

    access_token = (
        args.access_token or os.environ.get("HUBSPOT_ACCESS_TOKEN") or os.environ.get("HUBSPOT_MCP_ACCESS_TOKEN")
    )
    if not access_token:
        parser.error("Provide --access-token or set HUBSPOT_ACCESS_TOKEN / HUBSPOT_MCP_ACCESS_TOKEN env")

    trace_manager = TraceManager(project_name="manual-hubspot-mcp-test")
    component_attributes = ComponentAttributes(component_instance_name="manual-hubspot-mcp-tool")

    print("Connecting to HubSpot MCP server (shinzo-labs via npx)...")
    tool = await HubSpotMCPTool.from_access_token(
        trace_manager=trace_manager,
        component_attributes=component_attributes,
        access_token=access_token,
    )

    descriptions = tool.get_tool_descriptions()
    print(f"\n✅ Fetched {len(descriptions)} tool descriptions from HubSpot MCP server")
    print("\nAvailable tools:")
    for td in descriptions[:10]:
        print(f"  - {td.name}: {td.description}")
    if len(descriptions) > 10:
        print(f"  ... and {len(descriptions) - 10} more")

    try:
        if args.call_tool:
            tool_args = json.loads(args.tool_args) if args.tool_args else {}
            inputs = MCPToolInputs(tool_name=args.call_tool, tool_arguments=tool_args)
            print(f"\n🔧 Calling tool '{args.call_tool}' with args: {tool_args}")
            result = await tool._run_without_io_trace(inputs=inputs, ctx={})
            print(f"\n✅ Tool '{args.call_tool}' response:")
            print(f"   Output: {result.output}")
            if result.is_error:
                print("   ⚠️  Server marked this as an error")
        else:
            print("\n💡 Tip: Use --call-tool <tool_name> to test a specific tool")
            print('   Example: --call-tool crm_get_contact --tool-args \'{"objectId": "123"}\'')
    finally:
        await tool.close()


if __name__ == "__main__":
    asyncio.run(main())
