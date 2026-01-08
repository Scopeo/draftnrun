"""
Disposable FastMCP debug server with in-memory state.

Run:
    uv run python scripts/fastmcp_debug_server.py

Default SSE endpoint (per FastMCP): http://127.0.0.1:8000/sse
"""

from typing import Any

from fastmcp import FastMCP

app = FastMCP("debug-fastmcp")
STORE: dict[str, Any] = {"hello": "world"}


@app.tool()
def read_item(key: str) -> dict[str, Any]:
    print(f"[fastmcp] read_item key={key}", flush=True)
    return {"found": key in STORE, "value": STORE.get(key)}


@app.tool()
def write_item(key: str, value: Any) -> dict[str, Any]:
    print(f"[fastmcp] write_item key={key} value={value}", flush=True)
    STORE[key] = value
    return {"ok": True, "size": len(STORE)}


@app.tool()
def list_items() -> dict[str, Any]:
    print("[fastmcp] list_items", flush=True)
    return {"keys": sorted(STORE.keys())}


if __name__ == "__main__":
    app.run()
