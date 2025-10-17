from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
import logging
from sqlalchemy.orm import Session

from ada_backend.database.setup_db import get_db
from ada_backend.routers.auth_router import get_user_from_supabase_token
from ada_backend.schemas.auth_schema import SupabaseUser
from ada_backend.schemas.admin_tools_schema import (
    CreateSpecificApiToolRequest,
    CreatedSpecificApiToolResponse,
    ApiToolListResponse,
    ApiToolDetailResponse,
)
from ada_backend.services.admin_tools_service import (
    create_specific_api_tool_service,
    list_api_tools_service,
    get_api_tool_detail_service,
    update_api_tool_service,
    delete_api_tool_service,
)
from ada_backend.services.user_roles_service import is_user_super_admin

LOGGER = logging.getLogger(__name__)

# Use a distinct prefix to avoid clashing with the SQLAdmin UI at /admin
router = APIRouter(
    prefix="/admin-tools",
    tags=["Admin Tools"],
)


@router.post(
    "/api-tools",
    response_model=CreatedSpecificApiToolResponse,
)
async def create_specific_api_tool(
    payload: CreateSpecificApiToolRequest,
    user: Annotated[SupabaseUser, Depends(get_user_from_supabase_token)],
    session: Session = Depends(get_db),
):
    # Enforce global super-admin (user-level) using the same Edge Function
    try:
        is_super = await is_user_super_admin(user)
        if not is_super:
            raise HTTPException(status_code=403, detail="Super admin required")
        return create_specific_api_tool_service(
            session=session,
            payload=payload,
        )
    except HTTPException as e:
        LOGGER.exception(
            "HTTPException while creating specific API tool: %s | payload=%s",
            e,
            payload.model_dump() if hasattr(payload, "model_dump") else getattr(payload, "dict", lambda: payload)(),
        )
        raise e
    except ValueError as e:
        LOGGER.exception(
            "Validation error while creating specific API tool: %s | payload=%s",
            e,
            payload.model_dump() if hasattr(payload, "model_dump") else getattr(payload, "dict", lambda: payload)(),
        )
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        LOGGER.exception(
            "Unexpected error during specific API tool creation | payload=%s",
            payload.model_dump() if hasattr(payload, "model_dump") else getattr(payload, "dict", lambda: payload)(),
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to create specific API tool",
        ) from e


@router.get(
    "/api-tools",
    response_model=ApiToolListResponse,
)
async def list_api_tools(
    user: Annotated[SupabaseUser, Depends(get_user_from_supabase_token)],
    session: Session = Depends(get_db),
):
    try:
        is_super = await is_user_super_admin(user)
        if not is_super:
            raise HTTPException(status_code=403, detail="Super admin required")
        return list_api_tools_service(session=session)
    except HTTPException:
        raise
    except Exception as e:
        LOGGER.exception("Error listing API tools: %s", e)
        raise HTTPException(status_code=500, detail="Failed to list API tools") from e


@router.get(
    "/api-tools/{component_instance_id}",
    response_model=ApiToolDetailResponse,
)
async def get_api_tool(
    component_instance_id: UUID,
    user: Annotated[SupabaseUser, Depends(get_user_from_supabase_token)],
    session: Session = Depends(get_db),
):
    try:
        is_super = await is_user_super_admin(user)
        if not is_super:
            raise HTTPException(status_code=403, detail="Super admin required")
        return get_api_tool_detail_service(session=session, component_instance_id=component_instance_id)
    except ValueError as e:
        LOGGER.exception("API tool not found: %s", e)
        raise HTTPException(status_code=404, detail=str(e)) from e
    except HTTPException:
        raise
    except Exception as e:
        LOGGER.exception("Error getting API tool detail: %s", e)
        raise HTTPException(status_code=500, detail="Failed to get API tool") from e


@router.put(
    "/api-tools/{component_instance_id}",
    response_model=CreatedSpecificApiToolResponse,
)
async def update_api_tool(
    component_instance_id: UUID,
    payload: CreateSpecificApiToolRequest,
    user: Annotated[SupabaseUser, Depends(get_user_from_supabase_token)],
    session: Session = Depends(get_db),
):
    try:
        is_super = await is_user_super_admin(user)
        if not is_super:
            raise HTTPException(status_code=403, detail="Super admin required")
        return update_api_tool_service(session=session, component_instance_id=component_instance_id, payload=payload)
    except ValueError as e:
        LOGGER.exception("Validation error while updating API tool: %s", e)
        raise HTTPException(status_code=400, detail=str(e)) from e
    except HTTPException:
        raise
    except Exception as e:
        LOGGER.exception("Error updating API tool: %s", e)
        raise HTTPException(status_code=500, detail="Failed to update API tool") from e


@router.delete(
    "/api-tools/{component_instance_id}",
    status_code=204,
)
async def delete_api_tool(
    component_instance_id: UUID,
    user: Annotated[SupabaseUser, Depends(get_user_from_supabase_token)],
    session: Session = Depends(get_db),
):
    try:
        is_super = await is_user_super_admin(user)
        if not is_super:
            raise HTTPException(status_code=403, detail="Super admin required")
        delete_api_tool_service(session=session, component_instance_id=component_instance_id)
    except ValueError as e:
        LOGGER.exception("API tool not found: %s", e)
        raise HTTPException(status_code=404, detail=str(e)) from e
    except HTTPException:
        raise
    except Exception as e:
        LOGGER.exception("Error deleting API tool: %s", e)
        raise HTTPException(status_code=500, detail="Failed to delete API tool") from e
