# MCP Testing Scripts

Scripts for testing MCP (Model Context Protocol) integrations.

## Local MCP (stdio transport)

### `test_local_mcp_tool.py`
LocalMCPTool stdio runner / smoke test. Works with the bundled FastMCP debug server and any stdio MCP server
(e.g. `github-mcp-server stdio`).

```bash
uv run python scripts/mcp/test_local_mcp_tool.py --preset fastmcp

# GitHub MCP server (requires env var)
export GITHUB_PERSONAL_ACCESS_TOKEN="..."
uv run python scripts/mcp/test_local_mcp_tool.py --preset github
```

### `fastmcp_debug_server.py`
Simple FastMCP server for testing. Can be used with:
- **LocalMCPTool**: Via stdio (spawned by LocalMCPTool)
- **RemoteMCPTool**: Run as HTTP/SSE server and connect to `http://127.0.0.1:8000/sse`

```bash
# For SSE mode:
uv run python scripts/mcp/fastmcp_debug_server.py
```

## Remote MCP (HTTP/SSE transport)

### `manual_remote_mcp_test.py`
Test RemoteMCPTool with any MCP server using presets or manual configuration.

**Using presets (recommended):**
```bash
# Linear (SSE transport)
uv run python scripts/mcp/manual_remote_mcp_test.py --preset linear

# HubSpot (Streamable HTTP transport)
uv run python scripts/mcp/manual_remote_mcp_test.py --preset hubspot

# Rube (Streamable HTTP transport)
uv run python scripts/mcp/manual_remote_mcp_test.py --preset rube
```

**Manual configuration (custom servers):**
```bash
uv run python scripts/mcp/manual_remote_mcp_test.py \
    --server-url https://custom.mcp.server/endpoint \
    --api-key "$API_KEY" \
    --transport streamable_http
```

**Environment variables for presets:**
- Linear: `LINEAR_API_KEY`
- HubSpot: `HUBSPOT_MCP_ACCESS_TOKEN`
- Rube: `RUBE_API_KEY`

### `get_hubspot_oauth_token.py`
Helper to get HubSpot OAuth tokens for testing.

```bash
uv run python scripts/mcp/get_hubspot_oauth_token.py
```

## Architecture

```
LocalMCPTool (stdio)
  └── Spawns subprocess → fastmcp_debug_server.py
  └── Persistent session (state shared)

RemoteMCPTool (HTTP/SSE)
  └── Connects to running server
  └── Each call creates new connection
```
