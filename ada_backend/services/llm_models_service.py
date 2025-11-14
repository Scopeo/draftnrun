from sqlalchemy.orm import Session
from uuid import UUID

from ada_backend.repositories.llm_models_repository import (
    get_llm_models_by_capability,
    create_llm_model,
    delete_llm_model,
    update_llm_model,
    get_all_llm_models,
)
from ada_backend.schemas.llm_models_schema import LLMModelResponse, LLMModelUpdate
from ada_backend.database.models import SelectOption


def get_all_llm_models_service(session: Session) -> list[LLMModelResponse]:
    models = get_all_llm_models(session)
    print(models)
    return [
        LLMModelResponse(
            id=model.id,
            display_name=model.display_name,
            description=model.description,
            model_name=model.model_name,
            provider=model.provider,
            model_capacity=model.model_capacity,
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
    print("models")
    print(models)
    return [
        LLMModelResponse(
            id=model.id,
            display_name=model.display_name,
            description=model.description,
            model_name=model.model_name,
            provider=model.provider,
            model_capacity=model.model_capacity,
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
    display_name: str,
    model_description: str,
    model_capacity: list[str],
    model_provider: str,
    model_name: str,
) -> LLMModelResponse:

    created_llm_model = create_llm_model(
        session,
        display_name,
        model_description,
        model_capacity,
        model_provider,
        model_name,
    )
    return LLMModelResponse.model_validate(created_llm_model)


def delete_llm_model_service(session: Session, llm_model_id: UUID) -> None:
    delete_llm_model(session, llm_model_id)


def update_llm_model_service(
    session: Session,
    llm_model_id: UUID,
    display_name: str,
    model_name: str,
    description: str,
    model_capacity: list[str],
    provider: str,
) -> LLMModelResponse:
    updated_llm_model = LLMModelUpdate(
        id=llm_model_id,
        display_name=display_name,
        model_name=model_name,
        description=description,
        model_capacity=model_capacity,
        provider=provider,
    )
    updated_llm_model = update_llm_model(session, updated_llm_model)
    return LLMModelResponse.model_validate(updated_llm_model)
