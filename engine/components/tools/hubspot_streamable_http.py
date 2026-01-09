"""
Streamable HTTP client implementation for HubSpot MCP.

MCP Streamable HTTP transport:
- POST requests send JSON-RPC messages
- Responses come in POST response body (not SSE)
"""

import logging
from contextlib import asynccontextmanager

import anyio
import httpx
import mcp.types as types
from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream

LOGGER = logging.getLogger(__name__)


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
    read_stream_writer: MemoryObjectSendStream[types.JSONRPCMessage | Exception]
    read_stream: MemoryObjectReceiveStream[types.JSONRPCMessage | Exception]
    write_stream: MemoryObjectSendStream[types.JSONRPCMessage]
    write_stream_reader: MemoryObjectReceiveStream[types.JSONRPCMessage]

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
            async for message in write_stream_reader:
                try:
                    message_dict = (
                        message.model_dump(by_alias=True, mode="json", exclude_none=True)
                        if hasattr(message, "model_dump")
                        else message
                    )

                    headers = {"Content-Type": "application/json"}
                    if session_id:
                        headers["mcp-session-id"] = session_id

                    response = await client.post(url, json=message_dict, headers=headers)
                    response.raise_for_status()

                    if "mcp-session-id" in response.headers:
                        session_id = response.headers["mcp-session-id"]

                    if response.text.strip():
                        try:
                            response_data = response.json()
                            response_message = types.JSONRPCMessage.model_validate(response_data)
                            await read_stream_writer.send(response_message)
                        except Exception as e:
                            LOGGER.error(f"Error parsing response: {e}")
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
