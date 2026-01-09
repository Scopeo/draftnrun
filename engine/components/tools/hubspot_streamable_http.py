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
    client_provided = http_client is not None
    client = http_client

    if client is None:
        client = httpx.AsyncClient(timeout=httpx.Timeout(30.0, read=300.0))

    async def get_session_id() -> str | None:
        return session_id

    async def sse_reader():
        """Read SSE stream and forward messages to read_stream."""
        nonlocal session_id
        try:
            # Start GET request to SSE endpoint to establish session
            headers = {}
            if session_id:
                headers["mcp-session-id"] = session_id

            async with aconnect_sse(
                client,
                "GET",
                url,
                headers=headers,
            ) as event_source:
                event_source.response.raise_for_status()

                # Extract session ID from response headers if present
                if "mcp-session-id" in event_source.response.headers:
                    session_id = event_source.response.headers["mcp-session-id"]
                    LOGGER.debug(f"Session ID established: {session_id}")

                LOGGER.debug("SSE connection established")

                async for sse in event_source.aiter_sse():
                    if sse.data:
                        try:
                            # Parse JSON-RPC message from SSE data
                            message = types.JSONRPCMessage.model_validate_json(sse.data)
                            LOGGER.debug(f"Received server message: {message}")
                            await read_stream_writer.send(message)
                        except Exception as e:
                            LOGGER.error(f"Error parsing SSE message: {e}")
                            await read_stream_writer.send(e)
        except Exception as e:
            LOGGER.error(f"Error in SSE reader: {e}")
            await read_stream_writer.send(e)
        finally:
            await read_stream_writer.aclose()

    async def post_writer():
        """Send POST requests for messages in write_stream."""
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
                        session_id = response.headers["mcp-session-id"]
                        LOGGER.debug(f"Session ID updated: {session_id}")

                    # For Streamable HTTP, responses come via SSE, not POST response body
                    # The SSE reader will handle the actual response
                except Exception as e:
                    LOGGER.error(f"Error sending POST request: {e}")
                    await read_stream_writer.send(e)
        except Exception as e:
            LOGGER.error(f"Error in post_writer: {e}")
        finally:
            await write_stream.aclose()

    async with anyio.create_task_group() as tg:
        try:
            # Start SSE reader first to establish session
            tg.start_soon(sse_reader)
            # Small delay to let SSE connection establish
            await anyio.sleep(0.1)
            # Then start POST writer
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
