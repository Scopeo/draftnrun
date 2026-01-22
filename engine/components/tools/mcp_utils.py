"""
Streamable HTTP client implementation for MCP.

MCP Streamable HTTP transport:
- POST requests send JSON-RPC messages
- Responses come in POST response body (JSON or SSE format)
"""

import json
import logging
from contextlib import asynccontextmanager

import anyio
import httpx
import mcp.types as types
from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream
from mcp.shared.message import SessionMessage

LOGGER = logging.getLogger(__name__)


def _serialize_message_to_json(session_message: SessionMessage) -> dict:
    """
    Serialize SessionMessage to JSON dict for HTTP transport.

    Extracts the inner JSONRPCMessage and serializes it, exactly as the SDK
    does for SSE transport (see mcp.client.sse:141-145).
    """
    return session_message.message.model_dump(by_alias=True, mode="json", exclude_none=True)


def _deserialize_message_from_json(json_data: dict) -> SessionMessage:
    """
    Deserialize JSON dict to SessionMessage for SDK compatibility.

    Parses JSON to JSONRPCMessage and wraps it in SessionMessage, exactly as
    the SDK does for SSE transport (see mcp.client.sse:112-122).
    """
    message = types.JSONRPCMessage.model_validate(json_data)
    return SessionMessage(message=message)


def _parse_sse_response(sse_text: str) -> dict:
    """
    Parse SSE format response to extract JSON data from the first message.

    SSE format:
        event: message
        data: {"jsonrpc": "2.0", ...}

    Current implementation assumes one data message per SSE response, which matches
    observed behavior from Linear, HubSpot, and Rube MCP servers. If a server sends
    multiple messages in one response, only the first message will be processed.

    Args:
        sse_text: Raw SSE formatted text

    Returns:
        Parsed JSON data from the first 'data:' line
    """
    for line in sse_text.strip().split("\n"):
        line = line.strip()
        if line.startswith("data:"):
            json_str = line[5:].strip()
            if json_str:
                return json.loads(json_str)

    raise ValueError(f"No 'data:' line found in SSE response: {sse_text[:200]}")


@asynccontextmanager
async def streamable_http_client(
    url: str,
    http_client: httpx.AsyncClient | None = None,
    terminate_on_close: bool = True,
):
    """
    Streamable HTTP client for MCP protocol.

    Args:
        url: MCP server endpoint URL
        http_client: Pre-configured httpx client (must have auth headers)
        terminate_on_close: Whether to send DELETE request to terminate session

    Yields:
        Tuple of (read_stream, write_stream, get_session_id_callback)
    """
    read_stream_writer: MemoryObjectSendStream[SessionMessage | Exception]
    read_stream: MemoryObjectReceiveStream[SessionMessage | Exception]
    write_stream: MemoryObjectSendStream[SessionMessage]
    write_stream_reader: MemoryObjectReceiveStream[SessionMessage]

    read_stream_writer, read_stream = anyio.create_memory_object_stream(0)
    write_stream, write_stream_reader = anyio.create_memory_object_stream(0)

    session_id: str | None = None
    client_provided = http_client is not None
    client = http_client

    if client is None:
        client = httpx.AsyncClient(timeout=httpx.Timeout(30.0, read=300.0))

    async def get_session_id() -> str | None:
        return session_id

    async def post_writer():
        nonlocal session_id
        try:
            async for session_message in write_stream_reader:
                try:
                    message_dict = _serialize_message_to_json(session_message)

                    headers = {"Content-Type": "application/json"}
                    if session_id:
                        headers["mcp-session-id"] = session_id

                    response = await client.post(url, json=message_dict, headers=headers)
                    response.raise_for_status()

                    if "mcp-session-id" in response.headers:
                        session_id = response.headers["mcp-session-id"]

                    if response.text.strip():
                        try:
                            content_type = response.headers.get("content-type", "")

                            if "text/event-stream" in content_type:
                                response_data = _parse_sse_response(response.text)
                            else:
                                response_data = response.json()

                            session_message = _deserialize_message_from_json(response_data)
                            await read_stream_writer.send(session_message)
                        except Exception as e:
                            LOGGER.error(
                                f"Error parsing MCP response: {e} "
                                f"(Content-Type: {response.headers.get('content-type')})"
                            )
                            await read_stream_writer.send(e)
                except Exception as e:
                    LOGGER.error(f"Error sending POST request: {e}")
                    await read_stream_writer.send(e)
        finally:
            await read_stream_writer.aclose()
            await write_stream.aclose()

    async with anyio.create_task_group() as tg:
        try:
            tg.start_soon(post_writer)
            yield (read_stream, write_stream, get_session_id)
        finally:
            if terminate_on_close and session_id:
                try:
                    # Send DELETE to terminate session
                    await client.delete(url, headers={"mcp-session-id": session_id})
                except Exception as e:
                    LOGGER.warning(f"Error terminating session: {e}")
            if not client_provided:
                await client.aclose()
