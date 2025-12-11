from uuid import UUID
from typing import Annotated
import logging
import time
import threading
from collections import defaultdict
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from ada_backend.database.setup_db import get_db
from ada_backend.routers.auth_router import (
    user_has_access_to_organization_dependency,
    get_user_from_supabase_token,
    UserRights,
)
from ada_backend.schemas.auth_schema import SupabaseUser
from ada_backend.schemas.widget_schema import (
    WidgetSchema,
    WidgetCreateSchema,
    WidgetUpdateSchema,
    WidgetChatRequest,
)
from ada_backend.services.widget_service import (
    get_widget_public_config_service,
    widget_chat_service,
    list_widgets_service,
    get_widget_service,
    get_widget_by_project_service,
    create_widget_service,
    update_widget_service,
    regenerate_widget_key_service,
    delete_widget_service,
)
from ada_backend.repositories.widget_repository import get_widget_by_key
from ada_backend.services.errors import ProjectNotFound, EnvironmentNotFound, WidgetNotFound, WidgetDisabled
from ada_backend.services.user_roles_service import get_user_access_to_organization

# Use MEMBER/DEVELOPER (matching main branch)
_READER_RIGHT = UserRights.MEMBER
_WRITER_RIGHT = UserRights.DEVELOPER

router = APIRouter(tags=["Widget"])

LOGGER = logging.getLogger(__name__)


# Simple in-memory rate limiter with thread safety
# Note: In multi-server deployments, each server has its own limit store,
# so actual limits may be slightly higher than configured (limit * num_servers)
_rate_limit_store: dict[str, list[float]] = defaultdict(list)
_rate_limit_lock = threading.Lock()
RATE_LIMIT_CONFIG = 10  # requests per window
RATE_LIMIT_CHAT = 5  # requests per window for chat (more restrictive)
RATE_LIMIT_WINDOW = 60  # seconds


def _check_rate_limit(key: str, limit: int, window: int = RATE_LIMIT_WINDOW) -> bool:
    now = time.time()
    with _rate_limit_lock:
        _rate_limit_store[key] = [t for t in _rate_limit_store[key] if now - t < window]
        if len(_rate_limit_store[key]) >= limit:
            return False
        _rate_limit_store[key].append(now)
        return True


def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _check_origin_allowed(request: Request, allowed_origins: list[str]) -> bool:
    if not allowed_origins:
        LOGGER.debug("No allowed_origins configured, allowing all")
        return True

    origin = request.headers.get("Origin")
    LOGGER.debug(f"Origin check: origin={origin}, allowed_origins={allowed_origins}")
    if not origin:
        LOGGER.debug("No origin header, blocking request")
        return False

    parsed = urlparse(origin)
    netloc = parsed.netloc or parsed.path.split("/")[0]
    request_host = netloc.split(":")[0]
    LOGGER.debug(f"Parsed request_host: {request_host}")

    for pattern in allowed_origins:
        if pattern.startswith("*."):
            base_domain = pattern[2:]
            if request_host == base_domain or request_host.endswith("." + base_domain):
                LOGGER.debug(f"Origin {request_host} matched wildcard pattern {pattern}")
                return True
        elif request_host == pattern:
            LOGGER.debug(f"Origin {request_host} matched pattern {pattern}")
            return True

    LOGGER.debug(f"Origin {request_host} NOT in allowed list, blocking")
    return False


def _get_cors_headers(request: Request, allowed_origins: list[str]) -> dict[str, str]:
    origin = request.headers.get("Origin")
    if not origin:
        return {}

    if not allowed_origins:
        return {
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Credentials": "true",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
        }

    parsed = urlparse(origin)
    netloc = parsed.netloc or parsed.path.split("/")[0]
    request_host = netloc.split(":")[0]

    for pattern in allowed_origins:
        if pattern.startswith("*."):
            base_domain = pattern[2:]
            if request_host == base_domain or request_host.endswith("." + base_domain):
                return {
                    "Access-Control-Allow-Origin": origin,
                    "Access-Control-Allow-Credentials": "true",
                    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                    "Access-Control-Allow-Headers": "Content-Type",
                }
        elif request_host == pattern:
            return {
                "Access-Control-Allow-Origin": origin,
                "Access-Control-Allow-Credentials": "true",
                "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type",
            }

    return {}


@router.options("/widget/{widget_key}/config")
@router.options("/widget/{widget_key}/chat")
async def widget_preflight(
    widget_key: str,
    request: Request,
    session: Session = Depends(get_db),
) -> JSONResponse:
    widget = get_widget_by_key(session, widget_key)
    allowed_origins = []
    if widget and widget.config:
        allowed_origins = widget.config.get("allowed_origins", [])

    cors_headers = _get_cors_headers(request, allowed_origins)
    return JSONResponse(content={}, headers=cors_headers)


@router.get("/widget/{widget_key}/config")
def get_widget_config(
    widget_key: str,
    request: Request,
    session: Session = Depends(get_db),
) -> JSONResponse:
    try:
        widget = get_widget_by_key(session, widget_key)
        config = widget.config or {} if widget else {}

        # Check origin first to avoid leaking widget existence
        allowed_origins = config.get("allowed_origins", [])
        if not _check_origin_allowed(request, allowed_origins):
            raise HTTPException(status_code=403, detail="Origin not allowed")

        if not widget:
            raise WidgetNotFound(widget_key=widget_key)

        rate_limit = config.get("rate_limit_config", RATE_LIMIT_CONFIG)
        client_ip = get_client_ip(request)
        rate_key = f"config:{client_ip}:{widget_key}"
        if not _check_rate_limit(rate_key, rate_limit):
            raise HTTPException(status_code=429, detail="Rate limit exceeded. Please try again later.")

        result = get_widget_public_config_service(session, widget_key)
        cors_headers = _get_cors_headers(request, allowed_origins)
        return JSONResponse(content=result.model_dump(), headers=cors_headers)
    except WidgetNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except WidgetDisabled as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except HTTPException:
        raise
    except Exception as e:
        LOGGER.error(f"Failed to get widget config for {widget_key}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/widget/{widget_key}/chat")
async def widget_chat(
    widget_key: str,
    body: WidgetChatRequest,
    request: Request,
    session: Session = Depends(get_db),
) -> JSONResponse:
    try:
        LOGGER.debug(f"Widget chat endpoint hit for {widget_key}")
        widget = get_widget_by_key(session, widget_key)
        config = widget.config or {} if widget else {}
        LOGGER.debug(f"Widget config from DB: {config}")

        # Check origin first to avoid leaking widget existence
        allowed_origins = config.get("allowed_origins", [])
        if not _check_origin_allowed(request, allowed_origins):
            raise HTTPException(status_code=403, detail="Origin not allowed")

        if not widget:
            raise WidgetNotFound(widget_key=widget_key)

        rate_limit = config.get("rate_limit_chat", RATE_LIMIT_CHAT)
        client_ip = get_client_ip(request)
        rate_key = f"chat:{client_ip}:{widget_key}"
        if not _check_rate_limit(rate_key, rate_limit):
            raise HTTPException(status_code=429, detail="Rate limit exceeded. Please try again later.")

        result = await widget_chat_service(
            session=session,
            widget_key=widget_key,
            message=body.message,
            history=body.history,
            conversation_id=body.conversation_id,
        )
        cors_headers = _get_cors_headers(request, allowed_origins)
        return JSONResponse(content=result.model_dump(), headers=cors_headers)
    except WidgetNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except WidgetDisabled as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except HTTPException:
        raise
    except EnvironmentNotFound as e:
        LOGGER.error(f"Production environment not found for widget {widget_key}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=404, detail="Widget's workflow has no production deployment") from e
    except ConnectionError as e:
        LOGGER.error(f"Database connection error for widget {widget_key}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=503, detail="Database connection error") from e
    except ValueError as e:
        LOGGER.error(f"Error running widget chat for {widget_key}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        LOGGER.error(f"Failed to process chat for widget {widget_key}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/org/{organization_id}/widgets", response_model=list[WidgetSchema])
def list_widgets(
    organization_id: UUID,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_organization_dependency(allowed_roles=_READER_RIGHT.value))
    ],
    session: Session = Depends(get_db),
) -> list[WidgetSchema]:
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    try:
        return list_widgets_service(session, organization_id)
    except Exception as e:
        LOGGER.error(f"Failed to list widgets for organization {organization_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/widgets/{widget_id}", response_model=WidgetSchema)
async def get_widget(
    widget_id: UUID,
    user: Annotated[SupabaseUser, Depends(get_user_from_supabase_token)],
    session: Session = Depends(get_db),
) -> WidgetSchema:
    try:
        widget = get_widget_service(session, widget_id)
        access = await get_user_access_to_organization(user=user, organization_id=widget.organization_id)
        if access.role not in _READER_RIGHT.value:
            raise HTTPException(status_code=403, detail="You don't have access to this widget")
        return widget
    except WidgetNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except HTTPException:
        raise
    except Exception as e:
        LOGGER.error(f"Failed to get widget {widget_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/widgets/project/{project_id}", response_model=WidgetSchema | None)
async def get_widget_by_project(
    project_id: UUID,
    user: Annotated[SupabaseUser, Depends(get_user_from_supabase_token)],
    session: Session = Depends(get_db),
) -> WidgetSchema | None:
    try:
        widget = get_widget_by_project_service(session, project_id)
        if widget:
            access = await get_user_access_to_organization(user=user, organization_id=widget.organization_id)
            if access.role not in _READER_RIGHT.value:
                raise HTTPException(status_code=403, detail="You don't have access to this widget")
        return widget
    except HTTPException:
        raise
    except Exception as e:
        LOGGER.error(f"Failed to get widget for project {project_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/org/{organization_id}/widgets", response_model=WidgetSchema)
def create_widget(
    organization_id: UUID,
    data: WidgetCreateSchema,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_organization_dependency(allowed_roles=_WRITER_RIGHT.value))
    ],
    session: Session = Depends(get_db),
) -> WidgetSchema:
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    try:
        return create_widget_service(session, organization_id, data)
    except ProjectNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        LOGGER.error(f"Failed to create widget for organization {organization_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.patch("/widgets/{widget_id}", response_model=WidgetSchema)
async def update_widget(
    widget_id: UUID,
    data: WidgetUpdateSchema,
    user: Annotated[SupabaseUser, Depends(get_user_from_supabase_token)],
    session: Session = Depends(get_db),
) -> WidgetSchema:
    try:
        widget = get_widget_service(session, widget_id)
        access = await get_user_access_to_organization(user=user, organization_id=widget.organization_id)
        if access.role not in _WRITER_RIGHT.value:
            raise HTTPException(status_code=403, detail="You don't have permission to update this widget")
        return update_widget_service(session, widget_id, data)
    except WidgetNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except HTTPException:
        raise
    except Exception as e:
        LOGGER.error(f"Failed to update widget {widget_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/widgets/{widget_id}/regenerate-key", response_model=WidgetSchema)
async def regenerate_widget_key(
    widget_id: UUID,
    user: Annotated[SupabaseUser, Depends(get_user_from_supabase_token)],
    session: Session = Depends(get_db),
) -> WidgetSchema:
    try:
        widget = get_widget_service(session, widget_id)
        access = await get_user_access_to_organization(user=user, organization_id=widget.organization_id)
        if access.role not in UserRights.ADMIN.value:
            raise HTTPException(status_code=403, detail="You don't have permission to regenerate widget keys")
        return regenerate_widget_key_service(session, widget_id)
    except WidgetNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except HTTPException:
        raise
    except Exception as e:
        LOGGER.error(f"Failed to regenerate key for widget {widget_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.delete("/widgets/{widget_id}")
async def delete_widget(
    widget_id: UUID,
    user: Annotated[SupabaseUser, Depends(get_user_from_supabase_token)],
    session: Session = Depends(get_db),
) -> dict:
    try:
        widget = get_widget_service(session, widget_id)
        access = await get_user_access_to_organization(user=user, organization_id=widget.organization_id)
        if access.role not in UserRights.ADMIN.value:
            raise HTTPException(status_code=403, detail="You don't have permission to delete this widget")
        delete_widget_service(session, widget_id)
        return {"message": "Widget deleted successfully"}
    except WidgetNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except HTTPException:
        raise
    except Exception as e:
        LOGGER.error(f"Failed to delete widget {widget_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e
