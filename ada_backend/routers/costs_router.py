from fastapi import APIRouter
from typing import Annotated
from uuid import UUID
import logging
from sqlalchemy.orm import Session
from fastapi import Depends, status

from ada_backend.schemas.auth_schema import SupabaseUser
from ada_backend.routers.auth_router import UserRights, user_has_access_to_organization_dependency
from ada_backend.database.setup_db import get_db
from ada_backend.schemas.cost_schema import (
    UsageReadSchema,
    LLMCostResponse,
    LLMCost,
)
from ada_backend.services.costs_service import (
    get_usage_by_project_id_service,
    create_llm_cost_service,
    update_llm_cost_service,
    delete_llm_cost_service,
)

router = APIRouter(tags=["Costs"])
LOGGER = logging.getLogger(__name__)


@router.get("/projects/{project_id}/usage", response_model=list[UsageReadSchema])
def get_usage_by_project_id(
    project_id: UUID,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.READER.value))
    ],
    session: Session = Depends(get_db),
) -> list[UsageReadSchema]:
    return get_usage_by_project_id_service(session, project_id)


@router.post("/organizations/{organization_id}/llm-costs/{llm_model_id}", response_model=LLMCostResponse)
def create_llm_cost(
    organization_id: UUID,
    llm_model_id: UUID,
    llm_cost_create: LLMCost,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.WRITER.value))
    ],
    session: Session = Depends(get_db),
) -> LLMCostResponse:
    return create_llm_cost_service(
        session,
        llm_model_id,
        llm_cost_create.credits_per_input_token,
        llm_cost_create.credits_per_output_token,
        llm_cost_create.credits_per_call,
        llm_cost_create.credits_per_second,
    )


@router.patch("/organizations/{organization_id}/llm-costs/{llm_model_id}", response_model=LLMCostResponse)
def update_llm_cost(
    organization_id: UUID,
    llm_model_id: UUID,
    llm_cost_update: LLMCost,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.WRITER.value))
    ],
    session: Session = Depends(get_db),
) -> LLMCostResponse:
    return update_llm_cost_service(
        session,
        llm_model_id,
        llm_cost_update.credits_per_input_token,
        llm_cost_update.credits_per_output_token,
        llm_cost_update.credits_per_call,
        llm_cost_update.credits_per_second,
    )


@router.delete("/organizations/{organization_id}/llm-costs/{llm_model_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_llm_cost(
    organization_id: UUID,
    llm_model_id: UUID,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.WRITER.value))
    ],
    session: Session = Depends(get_db),
) -> None:
    return delete_llm_cost_service(session, llm_model_id)
