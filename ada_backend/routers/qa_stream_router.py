import json
import logging
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ada_backend.database.setup_db import get_db_session
from ada_backend.services.qa.qa_stream_service import (
    get_validated_qa_session,
    reconstruct_session_replay,
    stream_events,
    subscribe_to_session_stream,
)
from ada_backend.utils.websocket_auth import verify_project_ws_auth

LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/ws", tags=["QA stream"])


@router.websocket("/qa/{project_id}/{session_id}")
async def websocket_qa_stream(
    websocket: WebSocket,
    project_id: UUID,
    session_id: UUID,
):
    with get_db_session() as session:
        auth_ok = await verify_project_ws_auth(websocket, project_id, session)
        if not auth_ok:
            return
        await websocket.accept()

        qa_session = get_validated_qa_session(session, session_id, project_id)
        if not qa_session:
            await websocket.send_text(json.dumps({"type": "error", "message": "QA session not found"}))
            await websocket.close(code=4404, reason="QA session not found")
            return

        catchup_events, terminal_event = reconstruct_session_replay(session, qa_session)

    if terminal_event:
        for event in catchup_events:
            await websocket.send_text(event)
        await websocket.send_text(terminal_event)
        await websocket.close()
        return

    subscription = await subscribe_to_session_stream(session_id)
    if not subscription:
        LOGGER.warning("WebSocket QA session_id=%s: Redis unavailable, closing", session_id)
        await websocket.send_text(json.dumps({"type": "error", "message": "Redis unavailable"}))
        await websocket.close(code=4510, reason="Redis unavailable")
        return

    try:
        async for message in stream_events(subscription.queue):
            await websocket.send_text(message)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        LOGGER.exception("WebSocket QA session_id=%s error: %s", session_id, e)
    finally:
        subscription.stop()
        try:
            await websocket.close()
        except Exception:
            pass
