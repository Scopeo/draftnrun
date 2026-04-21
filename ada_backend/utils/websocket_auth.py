import logging
import urllib.parse
from uuid import UUID

from fastapi import HTTPException, WebSocket
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from ada_backend.routers.auth_router import (
    UserRights,
    get_user_from_supabase_token,
    user_has_access_to_project_dependency,
)

LOGGER = logging.getLogger(__name__)


def get_bearer_token_from_websocket(websocket: WebSocket) -> str | None:
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


async def verify_project_ws_auth(websocket: WebSocket, project_id: UUID, session: Session) -> bool:
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
