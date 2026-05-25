"""
Manual sanity script for NotionMCPTool.

What it does:
- Fetches the Notion access token from the database via Nango (connection_id).
- Spawns our internal FastMCP server via stdio.
- Lists the available tool descriptions.
- Optionally executes a single tool with JSON args and prints the raw output.

Usage:
    uv run python scripts/mcp/manual_notion_mcp_test.py --connection-id <uuid>

Optional: call a specific tool
    uv run python scripts/mcp/manual_notion_mcp_test.py \
        --connection-id <uuid> \
        --call-tool get_self

    uv run python scripts/mcp/manual_notion_mcp_test.py \
        --connection-id <uuid> \
        --call-tool search \
        --tool-args '{"query": "NeverDrop"}'

With direct token (bypass DB):
    uv run python scripts/mcp/manual_notion_mcp_test.py \
        --token <notion_access_token> \
        --call-tool get_self

Note: This is a dev helper for quick manual verification; no production dependency.
      Tests touch the REAL Notion workspace — prefix test data with TEST-.
"""

import argparse
import asyncio
import json
import os

from dotenv import load_dotenv

from engine.components.tools.mcp.shared import MCPToolInputs
from engine.components.tools.notion_mcp_tool import NotionMCPTool
from engine.components.types import ComponentAttributes
from engine.trace.trace_manager import TraceManager


async def get_token_from_db(connection_id: str) -> str:
    from uuid import UUID

    from ada_backend.database.setup_db import get_db_session
    from ada_backend.services.integration_service import get_oauth_access_token

    print(f"Fetching Notion access token for connection {connection_id}...")
    with get_db_session() as session:
        access_token = await get_oauth_access_token(
            session=session,
            oauth_connection_id=UUID(connection_id),
            provider_config_key="notion-neverdrop",
        )
    print("Token retrieved.")
    return access_token


async def main():
    load_dotenv("credentials.env")

    parser = argparse.ArgumentParser(description="Test Notion MCP Tool connection")
    token_group = parser.add_mutually_exclusive_group(required=True)
    token_group.add_argument("--connection-id", help="UUID of the Notion OAuth connection in the database")
    token_group.add_argument("--token", help="Direct Notion access token (bypasses DB)")
    parser.add_argument("--call-tool", help="Optional: tool name to invoke once (e.g., get_self)")
    parser.add_argument("--tool-args", help="Optional: JSON string of arguments to send with --call-tool")
    args = parser.parse_args()

    if args.token:
        access_token = args.token
    elif args.connection_id:
        access_token = await get_token_from_db(args.connection_id)
    else:
        env_token = os.environ.get("NOTION_ACCESS_TOKEN")
        if not env_token:
            print("ERROR: provide --connection-id, --token, or set NOTION_ACCESS_TOKEN")
            return
        access_token = env_token

    trace_manager = TraceManager(project_name="manual-notion-mcp-test")
    component_attributes = ComponentAttributes(component_instance_name="manual-notion-mcp-tool")

    tool = await NotionMCPTool.from_access_token(
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
            print(f"\nCalling '{args.call_tool}' with args: {json.dumps(tool_args, indent=2)}")
            result = await tool._run_without_io_trace(inputs=inputs, ctx={})
            print("\nResponse:")
            try:
                parsed = json.loads(result.output)
                print(json.dumps(parsed, indent=2, ensure_ascii=False))
            except (json.JSONDecodeError, TypeError):
                print(f"  output: {result.output}")
            if result.is_error:
                print("  (server marked this as an error)")
        else:
            print("\nTip: use --call-tool <name> --tool-args '{...}' to test a specific tool")
    finally:
        await tool.close()


if __name__ == "__main__":
    asyncio.run(main())
