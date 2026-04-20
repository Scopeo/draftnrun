import json
import logging
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ada_backend.database.setup_db import get_db_session
from ada_backend.services.graph_display_stream_service import (
    stream_events,
    subscribe_to_graph_updates,
)
from ada_backend.utils.websocket_auth import verify_project_ws_auth

LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/ws", tags=["Graph display stream"])


@router.websocket("/projects/{project_id}/graph-updates")
async def websocket_graph_display_stream(
    websocket: WebSocket,
    project_id: UUID,
):
    await websocket.accept()
    with get_db_session() as session:
        auth_ok = await verify_project_ws_auth(websocket, project_id, session)
        if not auth_ok:
            return

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
