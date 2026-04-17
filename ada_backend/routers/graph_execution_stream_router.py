"""
WebSocket endpoint to stream graph execution events for a project.
Subscribes to Redis Pub/Sub channel project-runs:{project_id} and relays:
  run.active, node.started, node.completed, run.completed, run.failed
"""

import asyncio
import json
import logging
import threading
from uuid import UUID

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from ada_backend.database.models import Run, RunStatus
from ada_backend.database.setup_db import get_db_session
from ada_backend.routers.auth_router import (
    UserRights,
    get_user_from_supabase_token,
    user_has_access_to_project_dependency,
)
from ada_backend.utils.redis_client import get_redis_client
from ada_backend.utils.websocket_auth import get_bearer_token_from_websocket

LOGGER = logging.getLogger(__name__)
PING_TIMEOUT_SECONDS = 25

router = APIRouter(prefix="/ws", tags=["Graph execution stream"])


async def _verify_ws_auth(websocket: WebSocket, project_id: UUID, session: Session) -> bool:
    bearer_token = get_bearer_token_from_websocket(websocket)
    if not bearer_token:
        await websocket.close(
            code=4401,
            reason="Missing authentication: provide Authorization (JWT) header or ?token= query parameter",
        )
        return False

    try:
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=bearer_token)
        user = await get_user_from_supabase_token(creds)
        await user_has_access_to_project_dependency(allowed_roles=UserRights.MEMBER.value)(
            project_id=project_id, user=user, session=session
        )
    except HTTPException as e:
        if e.status_code == 403:
            reason = (
                (e.detail or "Forbidden") if isinstance(e.detail, str) else "You don't have access to this project"
            )
            await websocket.close(code=4403, reason=reason[:123])
            return False
        if e.status_code == 404:
            await websocket.close(code=4404, reason="Project not found")
            return False
        LOGGER.debug("WebSocket JWT verification failed for project %s: %s", project_id, e)
        await websocket.close(code=4401, reason="Invalid or expired token")
        return False
    except Exception as e:
        LOGGER.debug("WebSocket JWT verification failed for project %s: %s", project_id, e)
        await websocket.close(code=4401, reason="Invalid or expired token")
        return False
    return True


def _get_running_runs(session: Session, project_id: UUID) -> list[dict]:
    runs = session.query(Run).filter(Run.project_id == project_id, Run.status == RunStatus.RUNNING).all()
    return [{"type": "run.active", "run_id": str(r.id), "graph_runner_id": None} for r in runs]


def _redis_subscriber_loop(
    project_id: UUID,
    queue: asyncio.Queue,
    loop: asyncio.AbstractEventLoop,
    stop_event: threading.Event,
) -> None:
    client = get_redis_client()
    if not client:
        LOGGER.warning("Redis subscriber project_id=%s: no Redis client", project_id)
        loop.call_soon_threadsafe(
            queue.put_nowait,
            json.dumps({"type": "error", "message": "Redis unavailable"}),
        )
        return
    pubsub = client.pubsub()
    channel = f"project-runs:{project_id}"
    pubsub.subscribe(channel)
    try:
        while not stop_event.is_set():
            message = pubsub.get_message(timeout=0.5)
            if message and message.get("type") == "message":
                data = message.get("data")
                if data is not None:
                    loop.call_soon_threadsafe(queue.put_nowait, data)
    finally:
        try:
            pubsub.unsubscribe(channel)
            pubsub.close()
        except Exception as e:
            LOGGER.debug("PubSub cleanup for %s: %s", channel, e)


async def _stream_events(queue: asyncio.Queue) -> None:
    """Yield JSON messages from the queue, sending pings on timeout."""
    while True:
        try:
            data = await asyncio.wait_for(queue.get(), timeout=PING_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            yield json.dumps({"type": "ping"})
            continue
        message = data if isinstance(data, str) else json.dumps(data)
        yield message


@router.websocket("/projects/{project_id}/graph-execution")
async def websocket_graph_execution_stream(
    websocket: WebSocket,
    project_id: UUID,
):
    with get_db_session() as session:
        auth_ok = await _verify_ws_auth(websocket, project_id, session)
        if not auth_ok:
            return
        await websocket.accept()

        if not get_redis_client():
            LOGGER.warning("WebSocket project_id=%s graph-execution: Redis unavailable", project_id)
            await websocket.send_text(json.dumps({"type": "error", "message": "Redis unavailable"}))
            await websocket.close(code=4510, reason="Redis unavailable")
            return

        catchup_events = _get_running_runs(session, project_id)

    queue: asyncio.Queue = asyncio.Queue()
    stop_event = threading.Event()
    loop = asyncio.get_event_loop()
    thread = threading.Thread(
        target=_redis_subscriber_loop,
        args=(project_id, queue, loop, stop_event),
        daemon=False,
    )
    thread.start()

    try:
        for event in catchup_events:
            await websocket.send_text(json.dumps(event))

        async for message in _stream_events(queue):
            await websocket.send_text(message)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        LOGGER.exception("WebSocket project_id=%s graph-execution error: %s", project_id, e)
    finally:
        stop_event.set()
        thread.join(timeout=2.0)
        try:
            await websocket.close()
        except Exception:
            pass
