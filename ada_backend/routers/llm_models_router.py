from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
import logging
from uuid import UUID
from typing import Annotated

from ada_backend.schemas.auth_schema import SupabaseUser
from ada_backend.routers.auth_router import UserRights, user_has_access_to_organization_dependency
from ada_backend.database.setup_db import get_db
from ada_backend.schemas.llm_models_schema import (
    LLMModelResponse,
    LLMModelCreate,
    LLMModelUpdate,
    ModelCapabilitiesResponse,
)
from ada_backend.services.llm_models_service import (
    get_all_llm_models_service,
    create_llm_model_service,
    delete_llm_model_service,
    update_llm_model_service,
    get_model_capabilities_service,
)


router = APIRouter(tags=["LLM Models"])
LOGGER = logging.getLogger(__name__)


@router.get("/organizations/{organization_id}/llm-models/capabilities", response_model=ModelCapabilitiesResponse)
def get_model_capabilities_endpoint(
    organization_id: UUID,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.ADMIN.value))
    ],
) -> ModelCapabilitiesResponse:
    """
    Get all available model capabilities that can be selected.
    Returns a list of capability options with value and human-readable label.
    """
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")

    return get_model_capabilities_service()


@router.get("/organizations/{organization_id}/llm-models", response_model=list[LLMModelResponse])
def get_all_llm_models_endpoint(
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.ADMIN.value))
    ],
    session: Session = Depends(get_db),
) -> list[LLMModelResponse]:
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    try:
        return get_all_llm_models_service(session)
    except Exception as e:
        LOGGER.error(f"Failed to get all LLM models: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/organizations/{organization_id}/llm-models", response_model=LLMModelResponse)
def create_llm_model_endpoint(
    organization_id: UUID,
    llm_model_data: LLMModelCreate,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.ADMIN.value))
    ],
    session: Session = Depends(get_db),
) -> LLMModelResponse:
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    try:
        return create_llm_model_service(
            session=session,
            llm_model_data=llm_model_data,
        )
    except Exception as e:
        LOGGER.error(f"Failed to create LLM model: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.delete("/organizations/{organization_id}/llm-models/{llm_model_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_llm_model_endpoint(
    llm_model_id: UUID,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.ADMIN.value))
    ],
    session: Session = Depends(get_db),
) -> None:
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    try:
        delete_llm_model_service(session, llm_model_id)
    except Exception as e:
        LOGGER.error(f"Failed to delete LLM model: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.patch("/organizations/{organization_id}/llm-models/{llm_model_id}", response_model=LLMModelResponse)
def update_llm_model_endpoint(
    organization_id: UUID,
    llm_model_id: UUID,
    llm_model_data: LLMModelUpdate,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.ADMIN.value))
    ],
    session: Session = Depends(get_db),
) -> LLMModelResponse:
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")
    try:
        return update_llm_model_service(
            session,
            llm_model_id,
            llm_model_data,
        )
    except Exception as e:
        LOGGER.error(f"Failed to update LLM model: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e
