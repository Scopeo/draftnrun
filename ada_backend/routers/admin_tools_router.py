import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ada_backend.database.setup_db import get_db
from ada_backend.routers.auth_router import ensure_super_admin_dependency
from ada_backend.schemas.admin_tools_schema import (
    CreatedSpecificApiToolResponse,
    CreateSpecificApiToolRequest,
)
from ada_backend.schemas.auth_schema import SupabaseUser
from ada_backend.services.admin_tools_service import (
    create_specific_api_tool_service,
)

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
    user: Annotated[SupabaseUser, Depends(ensure_super_admin_dependency())],
    session: Session = Depends(get_db),
):
    try:
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
