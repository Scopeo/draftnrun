from sqlalchemy.orm import Session
from uuid import UUID

from ada_backend.repositories.llm_models_repository import (
    get_llm_models_by_capability,
    create_llm_model,
    delete_llm_model,
    update_llm_model,
    get_all_llm_models,
)
from ada_backend.schemas.llm_models_schema import LLMModelResponse, LLMModelUpdate, LLMModelCreate, ModelCapabilityEnum
from ada_backend.database.models import SelectOption
from ada_backend.database import models as db


def get_all_llm_models_service(session: Session) -> list[LLMModelResponse]:
    models = get_all_llm_models(session)
    return [
        LLMModelResponse(
            id=model.id,
            display_name=model.display_name,
            description=model.description,
            model_name=model.model_name,
            provider=model.provider,
            model_capacity=[
                cap.value if isinstance(cap, ModelCapabilityEnum) else str(cap) for cap in (model.model_capacity or [])
            ],
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
        for model in models
    ]


def get_llm_models_by_capability_service(session: Session, capabilities: list[str]) -> list[LLMModelResponse]:
    """
    Get all LLM models that support ALL of the specified capabilities.
    """
    models = get_llm_models_by_capability(session, capabilities)
    return [
        LLMModelResponse(
            id=model.id,
            display_name=model.display_name,
            description=model.description,
            model_name=model.model_name,
            provider=model.provider,
            model_capacity=[
                cap.value if isinstance(cap, ModelCapabilityEnum) else str(cap) for cap in (model.model_capacity or [])
            ],
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
        for model in models
    ]


def convert_llm_models_to_select_options_service(models: list[LLMModelResponse]) -> list[SelectOption]:
    return [SelectOption(value=model.get_reference(), label=model.display_name) for model in models]


def get_llm_models_by_capability_select_options_service(
    session: Session,
    capabilities: list[str],
) -> list[SelectOption]:
    models = get_llm_models_by_capability_service(session, capabilities)
    return convert_llm_models_to_select_options_service(models)


def create_llm_model_service(
    session: Session,
    llm_model_data: LLMModelCreate,
) -> LLMModelResponse:
    # The ModelCapabilityList TypeDecorator handles enum-to-string conversion automatically
    created_llm_model = create_llm_model(
        session,
        llm_model_data.display_name,
        llm_model_data.description or "",
        llm_model_data.model_capacity,  # Pass enum list directly, TypeDecorator handles conversion
        llm_model_data.provider,
        llm_model_data.model_name,
    )
    return LLMModelResponse.model_validate(created_llm_model)


def delete_llm_model_service(session: Session, llm_model_id: UUID) -> None:
    delete_llm_model(session, llm_model_id)


def update_llm_model_service(
    session: Session,
    llm_model_id: UUID,
    llm_model_data: LLMModelUpdate,
) -> LLMModelResponse:

    llm_model = db.LLMModels(
        id=llm_model_id,
        display_name=llm_model_data.display_name,
        model_name=llm_model_data.model_name,
        description=llm_model_data.description,
        model_capacity=llm_model_data.model_capacity,
        provider=llm_model_data.provider,
    )
    updated_llm_model = update_llm_model(session, llm_model)
    return LLMModelResponse.model_validate(updated_llm_model)
