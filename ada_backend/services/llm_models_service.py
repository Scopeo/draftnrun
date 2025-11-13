from sqlalchemy.orm import Session
from uuid import UUID

from ada_backend.repositories.llm_models_repository import (
    get_llm_models_by_capability,
    create_llm_model,
    delete_llm_model,
    update_llm_model,
    get_all_llm_models,
)
from ada_backend.schemas.llm_models_schema import LLMModelsResponse, LLMModelsCreate, LLMModelsUpdate
from ada_backend.database.models import SelectOption, LLMModels


def get_all_llm_models_service(session: Session) -> list[LLMModelsResponse]:
    models = get_all_llm_models(session)
    return [LLMModelsResponse.model_validate(model) for model in models]


def get_llm_models_by_capability_service(session: Session, capabilities: list[str]) -> list[LLMModelsResponse]:
    """
    Get all LLM models that support ALL of the specified capabilities.
    """
    models = get_llm_models_by_capability(session, capabilities)
    return [LLMModelsResponse.model_validate(model) for model in models]


def convert_llm_models_to_select_options_service(models: list[LLMModelsResponse]) -> list[SelectOption]:
    return [SelectOption(value=model.reference, label=model.name) for model in models]


def get_llm_models_by_capability_select_options_service(
    session: Session,
    capabilities: list[str],
) -> list[SelectOption]:
    models = get_llm_models_by_capability_service(session, capabilities)
    return convert_llm_models_to_select_options_service(models)


def create_llm_model_service(session: Session, llm_model: LLMModelsCreate) -> LLMModelsResponse:
    created_llm_model = create_llm_model(
        session,
        LLMModels(
            name=llm_model.name,
            description=llm_model.description,
            reference=llm_model.provider + ":" + llm_model.name,
            provider=llm_model.provider,
            model_capacity=llm_model.model_capacity or [],
        ),
    )
    return LLMModelsResponse.model_validate(created_llm_model)


def delete_llm_model_service(session: Session, llm_model_id: UUID) -> None:
    delete_llm_model(session, llm_model_id)


def update_llm_model_service(session: Session, llm_model: LLMModelsUpdate) -> LLMModelsResponse:
    updated_llm_model = update_llm_model(session, llm_model)
    return LLMModelsResponse.model_validate(updated_llm_model)
