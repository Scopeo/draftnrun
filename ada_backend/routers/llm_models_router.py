from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import logging
from uuid import UUID
from typing import Annotated

from ada_backend.schemas.auth_schema import SupabaseUser
from ada_backend.routers.auth_router import UserRights, user_has_access_to_organization_dependency
from ada_backend.database.setup_db import get_db
from ada_backend.schemas.llm_models_schema import LLMModelsResponse, LLMModelsCreate, LLMModelsUpdate
from ada_backend.services.llm_models_service import (
    get_all_llm_models_service,
    create_llm_model_service,
    delete_llm_model_service,
    update_llm_model_service,
)


router = APIRouter(tags=["LLM Models"])
LOGGER = logging.getLogger(__name__)


@router.get("/llm-models", response_model=list[LLMModelsResponse])
def get_all_llm_models_endpoint(
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.ADMIN.value))
    ],
    session: Session = Depends(get_db),
) -> list[LLMModelsResponse]:
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    try:
        return get_all_llm_models_service(session)
    except Exception as e:
        LOGGER.error(f"Failed to get all LLM models: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/llm-models", response_model=LLMModelsResponse)
def create_llm_model_endpoint(
    llm_model: LLMModelsCreate,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.ADMIN.value))
    ],
    session: Session = Depends(get_db),
) -> LLMModelsResponse:
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    try:
        return create_llm_model_service(session, llm_model)
    except Exception as e:
        LOGGER.error(f"Failed to create LLM model: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.delete("/llm-models/{llm_model_id}", response_model=LLMModelsResponse)
def delete_llm_model_endpoint(
    llm_model_id: UUID,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.ADMIN.value))
    ],
    session: Session = Depends(get_db),
) -> LLMModelsResponse:
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    try:
        return delete_llm_model_service(session, llm_model_id)
    except Exception as e:
        LOGGER.error(f"Failed to delete LLM model: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.patch("/llm-models", response_model=LLMModelsResponse)
def update_llm_model_endpoint(
    llm_model: LLMModelsUpdate,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.ADMIN.value))
    ],
    session: Session = Depends(get_db),
) -> LLMModelsResponse:
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    try:
        return update_llm_model_service(session, llm_model)
    except Exception as e:
        LOGGER.error(f"Failed to update LLM model: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e
