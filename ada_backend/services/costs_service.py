from sqlalchemy.orm import Session
from uuid import UUID
from typing import Optional
from ada_backend.schemas.cost_schema import UsageReadSchema, LLMCostResponse
from ada_backend.repositories.costs_repository import (
    get_usage_by_project_id,
    get_usage_by_project_id_and_year_and_month,
    create_llm_cost,
    update_llm_cost,
    delete_llm_cost,
)


def get_usage_by_project_id_service(session: Session, project_id: UUID) -> list[UsageReadSchema]:
    usage = get_usage_by_project_id(session, project_id)
    return [UsageReadSchema.model_validate(u, from_attributes=True) for u in usage]


def get_usage_by_project_id_and_year_and_month_service(
    session: Session, project_id: UUID, year: int, month: int
) -> list[UsageReadSchema]:
    usage = get_usage_by_project_id_and_year_and_month(session, project_id, year, month)
    if usage is None:
        return []
    return [UsageReadSchema.model_validate(usage, from_attributes=True)]


def create_llm_cost_service(
    session: Session,
    llm_model_id: UUID,
    credits_per_input_token: Optional[float] = None,
    credits_per_output_token: Optional[float] = None,
    credits_per_call: Optional[float] = None,
    credits_per_second: Optional[float] = None,
) -> LLMCostResponse:
    llm_cost = create_llm_cost(
        session,
        llm_model_id,
        credits_per_input_token,
        credits_per_output_token,
        credits_per_call,
        credits_per_second,
    )
    return LLMCostResponse.model_validate(llm_cost, from_attributes=True)


def update_llm_cost_service(
    session: Session,
    llm_model_id: UUID,
    credits_per_input_token: Optional[float] = None,
    credits_per_output_token: Optional[float] = None,
    credits_per_call: Optional[float] = None,
    credits_per_second: Optional[float] = None,
) -> LLMCostResponse:
    llm_cost = update_llm_cost(
        session,
        llm_model_id,
        credits_per_input_token,
        credits_per_output_token,
        credits_per_call,
        credits_per_second,
    )
    return LLMCostResponse.model_validate(llm_cost, from_attributes=True)


def delete_llm_cost_service(session: Session, llm_model_id: UUID) -> None:
    return delete_llm_cost(session, llm_model_id)
