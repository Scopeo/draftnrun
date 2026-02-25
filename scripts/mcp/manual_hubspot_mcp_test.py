"""
Manual sanity script for HubSpotMCPTool.

What it does:
- Fetches the HubSpot access token from the database via Nango (connection_id).
- Spawns our internal FastMCP server via stdio.
- Lists the available tool descriptions.
- Optionally executes a single tool with JSON args and prints the raw output.

Usage:
    uv run python scripts/mcp/manual_hubspot_mcp_test.py --connection-id <uuid>

Optional: call a specific tool
    uv run python scripts/mcp/manual_hubspot_mcp_test.py \
        --connection-id <uuid> \
        --call-tool crm_get_contact \
        --tool-args '{"objectId": "123"}'

Note: This is a dev helper for quick manual verification; no production dependency.
      Tests touch the REAL HubSpot CRM — prefix test data with TEST-.
"""

import argparse
import asyncio
import json
from uuid import UUID

from dotenv import load_dotenv

from ada_backend.database.setup_db import get_db_session
from ada_backend.services.integration_service import get_oauth_access_token
from engine.components.tools.hubspot_mcp_tool import HubSpotMCPTool
from engine.components.tools.mcp.shared import MCPToolInputs
from engine.components.types import ComponentAttributes
from engine.trace.trace_manager import TraceManager


async def main():
    load_dotenv("credentials.env")

    parser = argparse.ArgumentParser(description="Test HubSpot MCP Tool connection")
    parser.add_argument(
        "--connection-id",
        required=True,
        help="UUID of the HubSpot OAuth connection in the database",
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

    print(f"Fetching HubSpot access token for connection {args.connection_id}...")
    with get_db_session() as session:
        access_token = await get_oauth_access_token(
            session=session,
            oauth_connection_id=UUID(args.connection_id),
            provider_config_key="hubspot",
        )
    print("Token retrieved.")

    trace_manager = TraceManager(project_name="manual-hubspot-mcp-test")
    component_attributes = ComponentAttributes(component_instance_name="manual-hubspot-mcp-tool")

    tool = HubSpotMCPTool.from_access_token(
        trace_manager=trace_manager,
        component_attributes=component_attributes,
        access_token=access_token,
    )

    descriptions = tool.get_tool_descriptions()
    print(f"\n{len(descriptions)} tools loaded:")
    for td in descriptions:
        print(f"  - {td.name}: {td.description[:80]}")

    try:
        if args.call_tool:
            tool_args = json.loads(args.tool_args) if args.tool_args else {}
            inputs = MCPToolInputs(tool_name=args.call_tool, tool_arguments=tool_args)
            print(f"\nCalling '{args.call_tool}' with args: {tool_args}")
            result = await tool._run_without_io_trace(inputs=inputs, ctx={})
            print("\nResponse:")
            print(f"  output: {result.output}")
            if result.is_error:
                print("  (server marked this as an error)")
        else:
            print("\nTip: use --call-tool <name> --tool-args '{...}' to test a specific tool")
    finally:
        await tool.close()


if __name__ == "__main__":
    asyncio.run(main())
