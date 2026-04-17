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
from ada_backend.services.graph_display_stream_service import (
    stream_events,
    subscribe_to_graph_updates,
)
from ada_backend.utils.websocket_auth import get_bearer_token_from_websocket

LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/ws", tags=["Graph display stream"])


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


@router.websocket("/projects/{project_id}/graph-updates")
async def websocket_graph_display_stream(
    websocket: WebSocket,
    project_id: UUID,
):
    with get_db_session() as session:
        auth_ok = await _verify_ws_auth(websocket, project_id, session)
        if not auth_ok:
            return
        await websocket.accept()

    subscription = await subscribe_to_graph_updates(project_id)
    if not subscription:
        LOGGER.warning("WebSocket project_id=%s graph-updates: Redis unavailable", project_id)
        await websocket.send_text(json.dumps({"type": "error", "message": "Redis unavailable"}))
        await websocket.close(code=4510, reason="Redis unavailable")
        return

    try:
        async for message in stream_events(subscription.queue):
            await websocket.send_text(message)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        LOGGER.exception("WebSocket project_id=%s graph-updates error: %s", project_id, e)
    finally:
        subscription.stop()
        try:
            await websocket.close()
        except Exception:
            pass
