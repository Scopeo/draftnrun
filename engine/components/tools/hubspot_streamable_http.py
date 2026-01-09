"""
Streamable HTTP client implementation for HubSpot MCP.

This is a simplified implementation of MCP Streamable HTTP transport.
It handles POST requests for sending JSON-RPC messages and SSE streams for receiving responses.

TODO: Replace with official mcp.client.streamable_http when available in mcp package.
"""

import logging
from contextlib import asynccontextmanager

import anyio
import httpx
import mcp.types as types
from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream
from httpx_sse import aconnect_sse

LOGGER = logging.getLogger(__name__)


@asynccontextmanager
async def streamable_http_client(
    url: str,
    http_client: httpx.AsyncClient | None = None,
    terminate_on_close: bool = True,
):
    """
    Streamable HTTP client for MCP protocol.

    This implementation:
    - Uses POST requests to send JSON-RPC messages
    - Uses SSE streams to receive responses
    - Manages session lifecycle

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
    session_established = anyio.Event()  # Signal when session ID is ready
    client_provided = http_client is not None
    client = http_client

    if client is None:
        client = httpx.AsyncClient(timeout=httpx.Timeout(30.0, read=300.0))

    async def get_session_id() -> str | None:
        return session_id

    async def sse_reader():
        """
        Read SSE stream for server-initiated messages (notifications).
        In Streamable HTTP, request/response messages come in POST response bodies.
        SSE is only for server → client notifications.
        """
        nonlocal session_id
        try:
            # Wait for session to be established via first POST
            LOGGER.debug("SSE reader waiting for session to be established...")
            await session_established.wait()
            LOGGER.debug(f"SSE reader proceeding with session ID: {session_id}")

            # Note: HubSpot MCP may not support SSE for notifications
            # If GET fails with 405, that's expected - just log and continue
            headers = {}
            if session_id:
                headers["mcp-session-id"] = session_id

            try:
                async with aconnect_sse(
                    client,
                    "GET",
                    url,
                    headers=headers,
                ) as event_source:
                    event_source.response.raise_for_status()
                    LOGGER.debug("SSE connection established for server notifications")

                    async for sse in event_source.aiter_sse():
                        if sse.data:
                            try:
                                # Parse JSON-RPC message from SSE data
                                message = types.JSONRPCMessage.model_validate_json(sse.data)
                                LOGGER.debug(f"Received server notification: {message}")
                                await read_stream_writer.send(message)
                            except Exception as e:
                                LOGGER.error(f"Error parsing SSE message: {e}")
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 405:
                    # Server doesn't support SSE for notifications - that's OK
                    LOGGER.debug("Server doesn't support SSE notifications (405) - continuing without it")
                else:
                    raise
        except Exception as e:
            LOGGER.debug(f"SSE reader ended: {e}")
        # Note: Don't close read_stream_writer here - post_writer is also using it

    async def post_writer():
        """Send POST requests for messages in write_stream and read responses."""
        nonlocal session_id
        try:
            async for message in write_stream_reader:
                try:
                    LOGGER.debug(f"Sending client message: {message}")

                    # Serialize JSON-RPC message
                    message_dict = (
                        message.model_dump(
                            by_alias=True,
                            mode="json",
                            exclude_none=True,
                        )
                        if hasattr(message, "model_dump")
                        else message
                    )

                    # Prepare headers
                    headers = {"Content-Type": "application/json"}
                    if session_id:
                        headers["mcp-session-id"] = session_id

                    # POST request with message
                    response = await client.post(
                        url,
                        json=message_dict,
                        headers=headers,
                    )
                    response.raise_for_status()

                    # Extract session ID from response headers if present
                    if "mcp-session-id" in response.headers:
                        new_session_id = response.headers["mcp-session-id"]
                        if session_id != new_session_id:
                            session_id = new_session_id
                            LOGGER.debug(f"Session ID established: {session_id}")
                            # Signal SSE reader that it can now connect (for notifications)
                            session_established.set()

                    # In Streamable HTTP, the response comes in the POST response body
                    # Parse and forward to read_stream
                    if response.text.strip():  # Check if there's any content
                        try:
                            response_data = response.json()
                            response_message = types.JSONRPCMessage.model_validate(response_data)
                            LOGGER.debug(f"Received response: {response_message}")
                            await read_stream_writer.send(response_message)
                        except Exception as e:
                            LOGGER.error(f"Error parsing response: {e}, body: {response.text[:200]}")
                            await read_stream_writer.send(e)
                    else:
                        LOGGER.debug("POST response has no body (might be session init)")
                except Exception as e:
                    LOGGER.error(f"Error sending POST request: {e}")
                    await read_stream_writer.send(e)
        except Exception as e:
            LOGGER.error(f"Error in post_writer: {e}")
        finally:
            await read_stream_writer.aclose()
            await write_stream.aclose()

    async with anyio.create_task_group() as tg:
        try:
            # Start both tasks in parallel
            # POST writer will establish session, then SSE reader will connect
            tg.start_soon(post_writer)
            tg.start_soon(sse_reader)

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
