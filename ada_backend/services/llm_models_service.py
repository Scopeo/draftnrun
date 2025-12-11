from sqlalchemy.orm import Session
from uuid import UUID

from ada_backend.repositories.llm_models_repository import (
    get_llm_models_by_capability,
    create_llm_model,
    delete_llm_model,
    update_llm_model,
    get_all_llm_models,
    llm_model_exists,
    get_model_id_by_name,
)
from ada_backend.repositories.credits_repository import (
    upsert_llm_cost,
    delete_llm_cost,
)
from ada_backend.schemas.llm_models_schema import (
    LLMModelResponse,
    LLMModelUpdate,
    LLMModelCreate,
    ModelCapabilityEnum,
    ModelCapabilitiesResponse,
    ModelCapabilityOption,
)
from ada_backend.database.models import SelectOption
from ada_backend.services.errors import LLMModelNotFound


def get_model_capabilities_service() -> ModelCapabilitiesResponse:
    """
    Get all available model capabilities that can be selected.
    Returns a list of capability options with value and human-readable label.
    """
    # Map enum values to human-readable labels
    capability_labels = {
        ModelCapabilityEnum.FILE: "File Processing",
        ModelCapabilityEnum.IMAGE: "Image Processing",
        ModelCapabilityEnum.CONSTRAINED_OUTPUT: "Constrained Output",
        ModelCapabilityEnum.FUNCTION_CALLING: "Function Calling",
        ModelCapabilityEnum.WEB_SEARCH: "Web Search",
        ModelCapabilityEnum.OCR: "OCR (Optical Character Recognition)",
        ModelCapabilityEnum.EMBEDDING: "Embedding",
        ModelCapabilityEnum.COMPLETION: "Text Completion",
        ModelCapabilityEnum.REASONING: "Reasoning",
    }

    capabilities = [
        ModelCapabilityOption(value=cap.value, label=capability_labels[cap]) for cap in ModelCapabilityEnum
    ]

    return ModelCapabilitiesResponse(capabilities=capabilities)


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
            credits_per_input_token=model.llm_cost.credits_per_input_token if model.llm_cost else None,
            credits_per_output_token=model.llm_cost.credits_per_output_token if model.llm_cost else None,
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
            credits_per_input_token=model.llm_cost.credits_per_input_token if model.llm_cost else None,
            credits_per_output_token=model.llm_cost.credits_per_output_token if model.llm_cost else None,
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


def get_model_id_by_name_service(session: Session, model_name: str) -> UUID | None:
    return get_model_id_by_name(session, model_name)


def create_llm_model_service(
    session: Session,
    llm_model_data: LLMModelCreate,
) -> LLMModelResponse:

    created_llm_model = create_llm_model(
        session,
        llm_model_data.display_name,
        llm_model_data.description or "",
        llm_model_data.model_capacity,
        llm_model_data.provider,
        llm_model_data.model_name,
    )

    upsert_llm_cost(
        session,
        llm_model_id=created_llm_model.id,
        credits_per_input_token=llm_model_data.credits_per_input_token,
        credits_per_output_token=llm_model_data.credits_per_output_token,
    )

    return LLMModelResponse.model_validate(created_llm_model)


def delete_llm_model_service(session: Session, llm_model_id: UUID) -> None:

    delete_llm_cost(session, llm_model_id)
    delete_llm_model(session, llm_model_id)


def update_llm_model_service(
    session: Session,
    llm_model_id: UUID,
    llm_model_data: LLMModelUpdate,
) -> LLMModelResponse:
    updated_llm_model = update_llm_model(
        session,
        llm_model_id=llm_model_id,
        display_name=llm_model_data.display_name,
        model_name=llm_model_data.model_name,
        description=llm_model_data.description,
        model_capacity=llm_model_data.model_capacity,
        provider=llm_model_data.provider,
    )
    if updated_llm_model is None:
        raise LLMModelNotFound(llm_model_id)

    upsert_llm_cost(
        session,
        llm_model_id=llm_model_id,
        credits_per_input_token=llm_model_data.credits_per_input_token,
        credits_per_output_token=llm_model_data.credits_per_output_token,
    )

    return LLMModelResponse.model_validate(updated_llm_model)


def llm_model_exists_service(
    session: Session,
    model_name: str,
    provider: str,
    model_capacity: list[str],
) -> bool:
    return llm_model_exists(
        session,
        model_name,
        provider,
        model_capacity,
    )
