"""
WebSocket endpoint to stream run events (node.started, node.completed, run.completed, run.failed)
by subscribing to Redis Pub/Sub channel run:{run_id} and relaying to the client.
"""

import asyncio
import json
import logging
import threading
import urllib.parse
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from ada_backend.database.setup_db import get_db
from ada_backend.repositories import run_repository
from ada_backend.routers.auth_router import (
    UserRights,
    get_user_from_supabase_token,
    user_has_access_to_project_dependency,
)
from ada_backend.services.api_key_service import verify_api_key, verify_project_access
from ada_backend.services.errors import ApiKeyAccessDenied
from ada_backend.services.run_service import stream_run_events
from ada_backend.utils.redis_client import get_redis_client

LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/ws", tags=["Run stream"])


def _get_api_key_from_websocket(websocket: WebSocket) -> str | None:
    """Extract api_key from WebSocket query string."""
    query_string = websocket.scope.get("query_string", b"").decode()
    params = urllib.parse.parse_qs(query_string)
    keys = params.get("api_key") or params.get("X-API-Key") or []
    return keys[0] if keys else None


def _get_bearer_token_from_websocket(websocket: WebSocket) -> str | None:
    """Extract Bearer token from WebSocket upgrade request headers."""
    headers = websocket.scope.get("headers") or []
    for name, value in headers:
        if name.lower() == b"authorization" and value.lower().startswith(b"bearer "):
            return value[7:].decode().strip()
    query_string = websocket.scope.get("query_string", b"").decode()
    params = urllib.parse.parse_qs(query_string)
    token_list = params.get("token") or params.get("authorization") or []
    token = token_list[0] if token_list else None
    if token and token.lower().startswith("bearer "):
        return token[7:].strip()
    return token if token else None


async def _verify_ws_auth(
    websocket: WebSocket,
    run_id: UUID,
    session: Session,
) -> UUID | None:
    """
    Verify API key or JWT (Bearer) and run access. Returns run's project_id on success, None on failure.
    Closes the WebSocket with an appropriate code on failure.
    """
    api_key = _get_api_key_from_websocket(websocket)
    bearer_token = _get_bearer_token_from_websocket(websocket)
    if api_key and bearer_token:
        await websocket.close(
            code=4400, reason="Provide either api_key (query) or Authorization (JWT), not both"
        )
        return None
    if not api_key and not bearer_token:
        await websocket.close(
            code=4401,
            reason="Missing authentication: provide api_key (query) or Authorization (JWT)",
        )
        return None

    run = run_repository.get_run(session, run_id)
    if not run:
        await websocket.close(code=4404, reason="Run not found")
        return None

    if api_key:
        cleaned = api_key.replace("\\n", "\n").strip('"')
        try:
            verified = verify_api_key(session, private_key=cleaned)
        except ValueError as e:
            LOGGER.debug("WebSocket API key verification failed for run %s: %s", run_id, e)
            await websocket.close(code=4401, reason="Invalid API key")
            return None
        try:
            verify_project_access(session, verified, run.project_id)
        except ApiKeyAccessDenied:
            await websocket.close(code=4403, reason="Forbidden")
            return None
        return run.project_id

    try:
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=bearer_token)
        user = await get_user_from_supabase_token(creds)
        await user_has_access_to_project_dependency(allowed_roles=UserRights.MEMBER.value)(
            project_id=run.project_id, user=user, session=session
        )
    except HTTPException as e:
        if e.status_code == 403:
            reason = (
                (e.detail or "Forbidden") if isinstance(e.detail, str) else "You don't have access to this project"
            )
            await websocket.close(code=4403, reason=reason[:123])  # WS close reason length limit
            return None
        if e.status_code == 404:
            await websocket.close(code=4404, reason="Project not found")
            return None
        LOGGER.debug("WebSocket JWT verification failed for run %s: %s", run_id, e)
        await websocket.close(code=4401, reason="Invalid or expired token")
        return None
    except Exception as e:
        LOGGER.debug("WebSocket JWT verification failed for run %s: %s", run_id, e)
        await websocket.close(code=4401, reason="Invalid or expired token")
        return None
    return run.project_id


def _redis_subscriber_loop(
    run_id: UUID,
    queue: asyncio.Queue,
    loop: asyncio.AbstractEventLoop,
    stop_event: threading.Event,
) -> None:
    """Run in a thread: subscribe to run:{run_id} and put messages into the asyncio queue."""
    client = get_redis_client()
    if not client:
        LOGGER.warning("Redis subscriber run_id=%s: no Redis client", run_id)
        loop.call_soon_threadsafe(
            queue.put_nowait,
            json.dumps({"type": "error", "message": "Redis unavailable"}),
        )
        return
    pubsub = client.pubsub()
    channel = f"run:{run_id}"
    pubsub.subscribe(channel)
    try:
        while not stop_event.is_set():
            message = pubsub.get_message(timeout=0.5)
            if message and message.get("type") == "message":
                data = message.get("data")
                if data is not None:
                    loop.call_soon_threadsafe(queue.put_nowait, data)
                    try:
                        evt = json.loads(data) if isinstance(data, str) else data
                        if evt.get("type") in ("run.completed", "run.failed"):
                            break
                    except Exception:
                        pass
    finally:
        try:
            pubsub.unsubscribe(channel)
            pubsub.close()
        except Exception as e:
            LOGGER.debug("PubSub cleanup for %s: %s", channel, e)


@router.websocket("/runs/{run_id}")
async def websocket_run_stream(
    websocket: WebSocket,
    run_id: UUID,
    session: Session = Depends(get_db),
):
    """
    Stream run events over WebSocket.
    Auth: api_key in query, or JWT (Authorization: Bearer header or ?token= for playground).
    Sends JSON messages: node.started, node.completed, run.completed, run.failed.
    """
    auth = await _verify_ws_auth(websocket, run_id, session)
    if auth is None:
        return
    await websocket.accept()

    if not get_redis_client():
        LOGGER.warning("WebSocket run_id=%s: Redis unavailable, closing", run_id)
        await websocket.send_text(json.dumps({"type": "error", "message": "Redis unavailable"}))
        await websocket.close(code=4510, reason="Redis unavailable")
        return

    queue: asyncio.Queue = asyncio.Queue()
    stop_event = threading.Event()
    loop = asyncio.get_event_loop()
    thread = threading.Thread(
        target=_redis_subscriber_loop,
        args=(run_id, queue, loop, stop_event),
        daemon=True,
    )
    thread.start()

    try:
        async for message in stream_run_events(session, run_id, queue):
            await websocket.send_text(message)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        LOGGER.exception("WebSocket run_id=%s error: %s", run_id, e)
    finally:
        stop_event.set()
        thread.join(timeout=2.0)
        try:
            await websocket.close()
        except Exception:
            pass
