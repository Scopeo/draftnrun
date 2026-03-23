import asyncio
import json
import logging
import threading
import urllib.parse
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from ada_backend.database.models import RunStatus
from ada_backend.database.setup_db import get_db, get_db_session
from ada_backend.repositories.qa_session_repository import get_qa_session
from ada_backend.repositories.quality_assurance_repository import get_outputs_by_graph_runner
from ada_backend.routers.auth_router import (
    UserRights,
    get_user_from_supabase_token,
    user_has_access_to_project_dependency,
)
from ada_backend.utils.redis_client import get_redis_client

LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/ws", tags=["QA stream"])

TERMINAL_EVENT_TYPES = ("qa.completed", "qa.failed")
PING_TIMEOUT_SECONDS = 60


def _get_bearer_token_from_websocket(websocket: WebSocket) -> str | None:
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
    project_id: UUID,
    session: Session,
) -> bool:
    bearer_token = _get_bearer_token_from_websocket(websocket)
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
        await websocket.close(code=4401, reason="Invalid or expired token")
        return False
    except Exception:
        await websocket.close(code=4401, reason="Invalid or expired token")
        return False
    return True


def _build_entry_catchup_events(db_session: Session, qa_session) -> list[str]:
    if qa_session.status == RunStatus.PENDING:
        return []
    if not qa_session.graph_runner_id or not qa_session.dataset_id:
        return []
    outputs = get_outputs_by_graph_runner(db_session, qa_session.dataset_id, qa_session.graph_runner_id)
    events = []
    for input_id, output in outputs:
        is_error = bool(output and output.startswith("Error: "))
        events.append(json.dumps({
            "type": "qa.entry.completed",
            "input_id": str(input_id),
            "output": output,
            "success": not is_error,
            "error": output if is_error else None,
        }))
    return events


def _build_terminal_event(qa_session) -> str | None:
    if qa_session.status == RunStatus.COMPLETED:
        return json.dumps({
            "type": "qa.completed",
            "summary": {
                "total": qa_session.total,
                "passed": qa_session.passed,
                "failed": qa_session.failed,
                "success_rate": (
                    (qa_session.passed / qa_session.total * 100) if qa_session.total else 0.0
                ),
            },
        })
    if qa_session.status == RunStatus.FAILED:
        return json.dumps({
            "type": "qa.failed",
            "error": qa_session.error or {"message": "Unknown error", "type": "UnknownError"},
        })
    return None


def _redis_qa_subscriber_loop(
    session_id: UUID,
    queue: asyncio.Queue,
    loop: asyncio.AbstractEventLoop,
    stop_event: threading.Event,
    subscribed_event: threading.Event | None = None,
) -> None:
    client = get_redis_client()
    if not client:
        LOGGER.warning("Redis subscriber session_id=%s: no Redis client", session_id)
        if subscribed_event:
            subscribed_event.set()
        loop.call_soon_threadsafe(
            queue.put_nowait,
            json.dumps({"type": "error", "message": "Redis unavailable"}),
        )
        return
    pubsub = client.pubsub()
    channel = f"qa:{session_id}"
    pubsub.subscribe(channel)
    if subscribed_event:
        subscribed_event.set()
    try:
        while not stop_event.is_set():
            message = pubsub.get_message(timeout=0.5)
            if message and message.get("type") == "message":
                data = message.get("data")
                if data is not None:
                    loop.call_soon_threadsafe(queue.put_nowait, data)
                    try:
                        evt = json.loads(data) if isinstance(data, str) else data
                        if evt.get("type") in TERMINAL_EVENT_TYPES:
                            break
                    except (json.JSONDecodeError, TypeError):
                        pass
    finally:
        try:
            pubsub.unsubscribe(channel)
            pubsub.close()
        except Exception as e:
            LOGGER.debug("PubSub cleanup for %s: %s", channel, e)


async def _stream_qa_events(queue: asyncio.Queue):
    while True:
        try:
            data = await asyncio.wait_for(queue.get(), timeout=PING_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            yield json.dumps({"type": "ping"})
            continue

        message = data if isinstance(data, str) else json.dumps(data)
        yield message

        try:
            evt = json.loads(data) if isinstance(data, str) else data
            if isinstance(evt, dict) and evt.get("type") in TERMINAL_EVENT_TYPES:
                return
        except (json.JSONDecodeError, TypeError):
            pass


@router.websocket("/qa/{project_id}/{session_id}")
async def websocket_qa_stream(
    websocket: WebSocket,
    project_id: UUID,
    session_id: UUID,
    session: Session = Depends(get_db),
):
    auth_ok = await _verify_ws_auth(websocket, project_id, session)
    if not auth_ok:
        return
    await websocket.accept()

    qa_session = get_qa_session(session, session_id)
    if not qa_session or qa_session.project_id != project_id:
        await websocket.send_text(json.dumps({"type": "error", "message": "QA session not found"}))
        await websocket.close(code=4404, reason="QA session not found")
        return

    terminal_event = _build_terminal_event(qa_session)
    if terminal_event:
        for event in _build_entry_catchup_events(session, qa_session):
            await websocket.send_text(event)
        await websocket.send_text(terminal_event)
        await websocket.close()
        return

    if not get_redis_client():
        LOGGER.warning("WebSocket QA session_id=%s: Redis unavailable, closing", session_id)
        await websocket.send_text(json.dumps({"type": "error", "message": "Redis unavailable"}))
        await websocket.close(code=4510, reason="Redis unavailable")
        return

    queue: asyncio.Queue = asyncio.Queue()
    stop_event = threading.Event()
    subscribed_event = threading.Event()
    loop = asyncio.get_event_loop()
    thread = threading.Thread(
        target=_redis_qa_subscriber_loop,
        args=(session_id, queue, loop, stop_event, subscribed_event),
        daemon=False,
    )
    thread.start()

    await asyncio.get_event_loop().run_in_executor(None, subscribed_event.wait, 2.0)
    with get_db_session() as fresh_session:
        fresh_qa_session = get_qa_session(fresh_session, session_id)
        if fresh_qa_session:
            for event in _build_entry_catchup_events(fresh_session, fresh_qa_session):
                queue.put_nowait(event)
            terminal = _build_terminal_event(fresh_qa_session)
            if terminal:
                queue.put_nowait(terminal)

    try:
        async for message in _stream_qa_events(queue):
            await websocket.send_text(message)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        LOGGER.exception("WebSocket QA session_id=%s error: %s", session_id, e)
    finally:
        stop_event.set()
        thread.join(timeout=2.0)
        try:
            await websocket.close()
        except Exception:
            pass
