from uuid import UUID
from typing import Optional

from pydantic import BaseModel

from ada_backend.database.models import ParameterType, SelectOption, UIComponent, UIComponentProperties
from ada_backend.database import models as db
from ada_backend.database.seed.constants import (
    COMPLETION_MODEL_IN_DB,
    EMBEDDING_MODEL_IN_DB,
    TEMPERATURE_IN_DB,
    VERBOSITY_IN_DB,
    REASONING_IN_DB,
)
from ada_backend.database.seed.supported_models import (
    get_models_by_capability,
    ModelCapability,
)
from settings import settings


def convert_models_to_select_options(models: list[dict[str, str]]) -> list[SelectOption]:
    """Convert model dictionaries to SelectOption objects"""
    select_options = []
    for model_dict in models:
        for label, value in model_dict.items():
            select_options.append(SelectOption(value=value, label=label))
    return select_options


def add_custom_llm_model(
    custom_models: dict[str, dict[str, str]],
    model_type: str,
    model_capacity: Optional[str] = None,
) -> list[SelectOption]:
    list_model_options = []
    for provider, provider_info in custom_models.items():
        models = provider_info.get(model_type)
        for model in models:
            if model_capacity is None or model.get(model_capacity):
                model_name = model.get("model_name")
                custom_llm_reference = f"{provider}:{model_name}"
                list_model_options.append(
                    SelectOption(
                        value=custom_llm_reference,
                        label=model_name,
                    )
                )
    return list_model_options


# TODO: Move to constants.py
# Define UUIDs for components and instances
COMPONENT_UUIDS: dict[str, UUID] = {
    "synthesizer": UUID("6f790dd1-06f6-4489-a655-1a618763a114"),
    "retriever": UUID("8baf68a9-1671-4ed5-8374-6ec218f5d9a6"),
    "cohere_reranker": UUID("dfdc8b87-610f-4ce0-8cf1-276e80bec32b"),
    "formatter": UUID("079512c6-28e2-455f-af2c-f196015534bd"),
    "vocabulary_search": UUID("323cfc43-76d9-4ae1-b950-2791faf798c2"),
    "rag_agent": UUID("fe26eac8-61c6-4158-a571-61fd680676c8"),
    "base_ai_agent": UUID("22292e7f-a3ba-4c63-a4c7-dd5c0c75cdaa"),
    "api_call_tool": UUID("674b8c1d-0cc6-4887-be92-e3a2906830ed"),
    "tavily_agent": UUID("449f8f59-7aff-4b2d-b244-d2fcc09f6651"),
    "web_search_openai_agent": UUID("d6020df0-a7e0-4d82-b731-0a653beef2e6"),
    "sql_tool": UUID("f7ddbfcb-6843-4ae9-a15b-40aa565b955b"),
    "sql_db_service": UUID("4014e6bd-9d2d-4142-8bdc-6dd7d9068011"),
    "llm_call": UUID("7a039611-49b3-4bfd-b09b-c0f93edf3b79"),
    "snowflake_db_service": UUID("d27b7f18-b27d-48fb-b813-ac6c7eef49f2"),
    "hybrid_synthesizer": UUID("303ff9a5-3264-472c-b69f-c2da5be3bac8"),
    "hybrid_rag_agent": UUID("69ce9852-00cb-4c9d-86fe-8b8926afa994"),
    "relevant_chunk_selector": UUID("9870dd91-53fd-426b-aa99-7639da706f45"),
    "react_sql_agent": UUID("c0f1a2b3-4d5e-6f7a-8b9c-0d1e2f3a4b5c"),
    "run_sql_query_tool": UUID("667420c1-e2ca-446f-8e54-e0edd7e660bf"),
    "document_search": UUID("79399392-25ba-4cea-9f25-2738765dc329"),
    "document_enhanced_llm_call_agent": UUID("6460b304-640c-4468-abd3-67bbff6902d4"),
    "document_react_loader_agent": UUID("1c2fdf5b-4a8d-4788-acb6-86b00124c7ce"),
    "ocr_call": UUID("a3b4c5d6-e7f8-9012-3456-789abcdef012"),
    "input": UUID("01357c0b-bc99-44ce-a435-995acc5e2544"),
    "filter": UUID("02468c0b-bc99-44ce-a435-995acc5e2545"),
    "gmail_sender": UUID("af96bb40-c9ea-4851-a663-f0e64363fcb2"),
    "python_code_runner": UUID("e2b00000-0000-1111-2222-333333333333"),
    "terminal_command_runner": UUID("e2b10000-1111-2222-3333-444444444444"),
    "linkup_search_tool": UUID("f3e45678-9abc-def0-1234-56789abcdef0"),
    "pdf_generation": UUID("428baac0-0c5f-4374-b2de-8075218082b4"),
    "project_reference": UUID("4c8f9e2d-1a3b-4567-8901-234567890abc"),
    "chunk_processor": UUID("5d9f0f3e-2b4c-5678-9012-345678901bcd"),
    "docx_generation": UUID("b5195a0f-94f5-4f5c-8804-32dd19b16833"),
    "static_responder": UUID("1F7334BE-7164-4440-BBF3-E986EED0388F"),
}

DEFAULT_MODEL = "openai:gpt-5-mini"

# Get models by capability and convert to select options
COMPLETION_MODELS = [
    SelectOption(value=model["reference"], label=model["name"])
    for model in get_models_by_capability(ModelCapability.COMPLETION)
]

FUNCTION_CALLING_MODELS = [
    SelectOption(value=model["reference"], label=model["name"])
    for model in get_models_by_capability(ModelCapability.FUNCTION_CALLING)
]

EMBEDDING_MODELS = [
    SelectOption(value=model["reference"], label=model["name"])
    for model in get_models_by_capability(ModelCapability.EMBEDDING)
]

WEB_SEARCH_MODELS = [
    SelectOption(value=model["reference"], label=model["name"])
    for model in get_models_by_capability(ModelCapability.WEB_SEARCH)
]

OCR_MODELS = [
    SelectOption(value=model["reference"], label=model["name"])
    for model in get_models_by_capability(ModelCapability.OCR)
]

COMPLETION_MODELS.extend(
    add_custom_llm_model(settings.custom_models, "completion_models", "constrained_completion_with_pydantic")
)
FUNCTION_CALLING_MODELS.extend(add_custom_llm_model(settings.custom_models, "completion_models", "function_calling"))

EMBEDDING_MODELS.extend(add_custom_llm_model(settings.custom_models, "embedding_models"))


class ParameterLLMConfig(BaseModel):
    param_name: str
    param_id: UUID


def build_completion_service_config_definitions(
    component_id: UUID,
    params_to_seed: list[ParameterLLMConfig],
    definitions: list[db.ComponentParameterDefinition] = [],
) -> list[db.ComponentParameterDefinition]:
    """
    Simple helper function to avoid code duplication.
    params_to_seed is a list of parameters to seed for the given component.
    options: [
        "completion_model",
        "temperature",
        "api_key",
    ]
    """
    for param in params_to_seed:
        if param.param_name == COMPLETION_MODEL_IN_DB:
            definitions.append(
                db.ComponentParameterDefinition(
                    id=param.param_id,
                    component_id=component_id,
                    name=COMPLETION_MODEL_IN_DB,
                    type=ParameterType.STRING,
                    nullable=False,
                    default=DEFAULT_MODEL,
                    ui_component=UIComponent.SELECT,
                    ui_component_properties=UIComponentProperties(
                        options=COMPLETION_MODELS,
                        label="Model Name",
                    ).model_dump(exclude_unset=True, exclude_none=True),
                )
            )
        if param.param_name == TEMPERATURE_IN_DB:
            definitions.append(
                db.ComponentParameterDefinition(
                    id=param.param_id,
                    component_id=component_id,
                    name=TEMPERATURE_IN_DB,
                    type=ParameterType.FLOAT,
                    nullable=False,
                    default="1.0",
                    ui_component=UIComponent.SLIDER,
                    ui_component_properties=UIComponentProperties(
                        label="Temperature",
                        placeholder="Enter temperature, it is different for each model, check the model documentation",
                        min=0,
                        max=2,
                        step=0.01,
                        marks=True,
                    ).model_dump(exclude_unset=True, exclude_none=True),
                    is_advanced=True,
                )
            )

        if param.param_name == VERBOSITY_IN_DB:
            definitions.append(
                db.ComponentParameterDefinition(
                    id=param.param_id,
                    component_id=component_id,
                    name=VERBOSITY_IN_DB,
                    type=ParameterType.STRING,
                    nullable=True,
                    default=None,
                    ui_component=UIComponent.SELECT,
                    ui_component_properties=UIComponentProperties(
                        label="Verbosity",
                        options=[
                            SelectOption(value="low", label="Low"),
                            SelectOption(value="medium", label="Medium"),
                            SelectOption(value="high", label="High"),
                        ],
                        placeholder="Select verbosity level useful only for GPT 5 models",
                    ).model_dump(exclude_unset=True, exclude_none=True),
                    is_advanced=True,
                )
            )

        if param.param_name == REASONING_IN_DB:
            definitions.append(
                db.ComponentParameterDefinition(
                    id=param.param_id,
                    component_id=component_id,
                    name=REASONING_IN_DB,
                    type=ParameterType.STRING,
                    nullable=True,
                    default=None,
                    ui_component=UIComponent.SELECT,
                    ui_component_properties=UIComponentProperties(
                        label="Reasoning",
                        options=[
                            SelectOption(value="minimal", label="Minimal"),
                            SelectOption(value="medium", label="Medium"),
                            SelectOption(value="high", label="High"),
                            SelectOption(value="low", label="Low"),
                        ],
                        placeholder="Select reasoning level useful only for GPT 5 models",
                    ).model_dump(exclude_unset=True, exclude_none=True),
                    is_advanced=True,
                )
            )
        if param.param_name == "api_key":
            definitions.append(
                db.ComponentParameterDefinition(
                    id=param.param_id,
                    component_id=component_id,
                    name="api_key",
                    type=ParameterType.LLM_API_KEY,
                    nullable=True,
                )
            )
    return definitions


def build_function_calling_service_config_definitions(
    component_id: UUID,
    params_to_seed: list[ParameterLLMConfig],
) -> list[db.ComponentParameterDefinition]:
    """
    Simple helper function to avoid code duplication.
    params_to_seed is a list of parameters to seed for the given component.
    options: [
        "completion_model",
        "temperature",
        "api_key",
    ]
    """
    definitions: list[db.ComponentParameterDefinition] = []
    for param in params_to_seed:
        if param.param_name == COMPLETION_MODEL_IN_DB:
            definitions.append(
                db.ComponentParameterDefinition(
                    id=param.param_id,
                    component_id=component_id,
                    name=COMPLETION_MODEL_IN_DB,
                    type=ParameterType.STRING,
                    nullable=False,
                    default=DEFAULT_MODEL,
                    ui_component=UIComponent.SELECT,
                    ui_component_properties=UIComponentProperties(
                        options=FUNCTION_CALLING_MODELS,
                        label="Model Name",
                    ).model_dump(exclude_unset=True, exclude_none=True),
                )
            )
        if param.param_name == TEMPERATURE_IN_DB:
            definitions.append(
                db.ComponentParameterDefinition(
                    id=param.param_id,
                    component_id=component_id,
                    name=TEMPERATURE_IN_DB,
                    type=ParameterType.FLOAT,
                    nullable=False,
                    default="1.0",
                    ui_component=UIComponent.SLIDER,
                    ui_component_properties=UIComponentProperties(
                        label="Temperature",
                        placeholder="Enter temperature, it is different for each model, check the model documentation",
                        min=0,
                        max=2,
                        step=0.01,
                        marks=True,
                    ).model_dump(exclude_unset=True, exclude_none=True),
                    is_advanced=True,
                )
            )
        if param.param_name == "api_key":
            definitions.append(
                db.ComponentParameterDefinition(
                    id=param.param_id,
                    component_id=component_id,
                    name="api_key",
                    type=ParameterType.LLM_API_KEY,
                    nullable=True,
                )
            )
    return definitions


def build_embedding_service_config_definitions(
    component_id: UUID,
    params_to_seed: list[ParameterLLMConfig],
) -> list[db.ComponentParameterDefinition]:
    """
    Simple helper function to avoid code duplication.
    params_to_seed is a list of parameters to seed for the given component.
    options: [
        "embedding_model",
        "api_key",
    ]
    """
    definitions: list[db.ComponentParameterDefinition] = []
    for param in params_to_seed:
        if param.param_name == EMBEDDING_MODEL_IN_DB:
            definitions.append(
                db.ComponentParameterDefinition(
                    id=param.param_id,
                    component_id=component_id,
                    name=EMBEDDING_MODEL_IN_DB,
                    type=ParameterType.STRING,
                    nullable=False,
                    default=EMBEDDING_MODELS[0].value,
                    ui_component=UIComponent.SELECT,
                    ui_component_properties=UIComponentProperties(
                        options=EMBEDDING_MODELS,
                        label="Embedding Model Name",
                    ).model_dump(exclude_unset=True, exclude_none=True),
                )
            )
        if param.param_name == "api_key":
            definitions.append(
                db.ComponentParameterDefinition(
                    id=param.param_id,
                    component_id=component_id,
                    name="api_key",
                    type=ParameterType.STRING,
                    nullable=False,
                    default="",
                )
            )
    return definitions


def build_web_service_config_definitions(
    component_id: UUID,
    params_to_seed: list[ParameterLLMConfig],
) -> list[db.ComponentParameterDefinition]:
    """
    Simple helper function to avoid code duplication.
    params_to_seed is a list of parameters to seed for the given component.
    options: [
        "completion_model",
        "api_key",
    ]
    """
    definitions: list[db.ComponentParameterDefinition] = []
    for param in params_to_seed:
        if param.param_name == COMPLETION_MODEL_IN_DB:
            definitions.append(
                db.ComponentParameterDefinition(
                    id=param.param_id,
                    component_id=component_id,
                    name=COMPLETION_MODEL_IN_DB,
                    type=ParameterType.STRING,
                    nullable=False,
                    default=DEFAULT_MODEL,
                    ui_component=UIComponent.SELECT,
                    ui_component_properties=UIComponentProperties(
                        options=WEB_SEARCH_MODELS,
                        label="Model Name",
                    ).model_dump(exclude_unset=True, exclude_none=True),
                )
            )
        if param.param_name == "api_key":
            definitions.append(
                db.ComponentParameterDefinition(
                    id=param.param_id,
                    component_id=component_id,
                    name="api_key",
                    type=ParameterType.LLM_API_KEY,
                    nullable=True,
                )
            )
    return definitions


def build_ocr_service_config_definitions(
    component_id: UUID,
    params_to_seed: list[ParameterLLMConfig],
) -> list[db.ComponentParameterDefinition]:
    """
    Simple helper function to avoid code duplication.
    params_to_seed is a list of parameters to seed for the given component.
    options: [
        "completion_model",
        "api_key",
    ]
    """
    definitions: list[db.ComponentParameterDefinition] = []
    for param in params_to_seed:
        if param.param_name == COMPLETION_MODEL_IN_DB:
            definitions.append(
                db.ComponentParameterDefinition(
                    id=param.param_id,
                    component_id=component_id,
                    name=COMPLETION_MODEL_IN_DB,
                    type=ParameterType.STRING,
                    nullable=False,
                    default=OCR_MODELS[0].value,
                    ui_component=UIComponent.SELECT,
                    ui_component_properties=UIComponentProperties(
                        options=OCR_MODELS,
                        label="Model Name",
                    ).model_dump(exclude_unset=True, exclude_none=True),
                )
            )
        if param.param_name == "api_key":
            definitions.append(
                db.ComponentParameterDefinition(
                    id=param.param_id,
                    component_id=component_id,
                    name="api_key",
                    type=ParameterType.LLM_API_KEY,
                    nullable=True,
                )
            )
    return definitions
