import json
import logging
from uuid import UUID

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from ada_backend.database.setup_db import get_db_session
from ada_backend.routers.auth_router import (
    UserRights,
    get_user_from_supabase_token,
    user_has_access_to_project_dependency,
)
from ada_backend.services.qa.qa_stream_service import (
    get_validated_qa_session,
    reconstruct_session_replay,
    stream_events,
    subscribe_to_session_stream,
)
from ada_backend.utils.websocket_auth import get_bearer_token_from_websocket

LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/ws", tags=["QA stream"])


async def _verify_ws_auth(
    websocket: WebSocket,
    project_id: UUID,
    session: Session,
) -> bool:
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
        await websocket.close(code=4401, reason="Invalid or expired token")
        return False
    except Exception:
        await websocket.close(code=4401, reason="Invalid or expired token")
        return False
    return True


@router.websocket("/qa/{project_id}/{session_id}")
async def websocket_qa_stream(
    websocket: WebSocket,
    project_id: UUID,
    session_id: UUID,
):
    with get_db_session() as session:
        auth_ok = await _verify_ws_auth(websocket, project_id, session)
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
