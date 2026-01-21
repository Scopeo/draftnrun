"""
Disposable FastMCP debug server with in-memory state.

Run:
    uv run python scripts/mcp/fastmcp_debug_server.py

Default SSE endpoint (per FastMCP): http://127.0.0.1:8000/sse

NOTE: For LocalMCPTool (stdio), state IS shared via persistent session.
For SSE transport, run this server and connect via RemoteMCPTool.
"""

from typing import Any

from fastmcp import FastMCP

app = FastMCP("debug-fastmcp")
STORE: dict[str, Any] = {"hello": "world"}


@app.tool()
def read_item(key: str) -> dict[str, Any]:
    return {"found": key in STORE, "value": STORE.get(key)}


@app.tool()
def write_item(key: str, value: Any) -> dict[str, Any]:
    STORE[key] = value
    return {"ok": True, "size": len(STORE)}


@app.tool()
def list_items() -> dict[str, Any]:
    return {"keys": sorted(STORE.keys())}


if __name__ == "__main__":
    app.run()
