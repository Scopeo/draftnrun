import logging
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy.orm import Session

from ada_backend.database import models as db
from ada_backend.database.models import ParameterType, SelectOption, UIComponent, UIComponentProperties
from ada_backend.database.seed.constants import (
    COMPLETION_MODEL_IN_DB,
    EMBEDDING_MODEL_IN_DB,
    REASONING_IN_DB,
    TEMPERATURE_IN_DB,
    VERBOSITY_IN_DB,
)
from ada_backend.schemas.llm_models_schema import LLMModelCreate, ModelCapabilityEnum
from ada_backend.services.llm_models_service import create_llm_model_service, llm_model_exists_exact_match_service
from settings import settings

LOGGER = logging.getLogger(__name__)


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
    "document_enhanced_llm_call": UUID("6460b304-640c-4468-abd3-67bbff6902d4"),
    "document_react_loader_agent": UUID("1c2fdf5b-4a8d-4788-acb6-86b00124c7ce"),
    "ocr_call": UUID("a3b4c5d6-e7f8-9012-3456-789abcdef012"),
    "start": UUID("01357c0b-bc99-44ce-a435-995acc5e2544"),
    "filter": UUID("02468c0b-bc99-44ce-a435-995acc5e2545"),
    "gmail_sender": UUID("af96bb40-c9ea-4851-a663-f0e64363fcb2"),
    "python_code_runner": UUID("e2b00000-0000-1111-2222-333333333333"),
    "terminal_command_runner": UUID("e2b10000-1111-2222-3333-444444444444"),
    "docx_template": UUID("e2b20000-2222-3333-4444-555555555555"),
    "linkup_search_tool": UUID("f3e45678-9abc-def0-1234-56789abcdef0"),
    "retriever_tool": UUID("9f1c6c7a-6c8a-4b1e-9b3e-6a0b2f9c8e4d"),
    "pdf_generation": UUID("428baac0-0c5f-4374-b2de-8075218082b4"),
    "project_reference": UUID("4c8f9e2d-1a3b-4567-8901-234567890abc"),
    "chunk_processor": UUID("5d9f0f3e-2b4c-5678-9012-345678901bcd"),
    "docx_generation": UUID("b5195a0f-94f5-4f5c-8804-32dd19b16833"),
    "static_responder": UUID("1F7334BE-7164-4440-BBF3-E986EED0388F"),
    "remote_mcp_tool": UUID("de3e606d-1f9d-4d74-b64f-bbde9ad6f0f4"),
    "table_lookup": UUID("3a4b5c6d-7e8f-9012-3456-789abcdef123"),
    "if_else": UUID("b3887e9d-9881-419c-ab7b-30b38409d34d"),
}
COMPONENT_VERSION_UUIDS: dict[str, UUID] = {
    "synthesizer": UUID("6f790dd1-06f6-4489-a655-1a618763a114"),
    "retriever": UUID("8baf68a9-1671-4ed5-8374-6ec218f5d9a6"),
    "cohere_reranker": UUID("dfdc8b87-610f-4ce0-8cf1-276e80bec32b"),
    "formatter": UUID("079512c6-28e2-455f-af2c-f196015534bd"),
    "vocabulary_search": UUID("323cfc43-76d9-4ae1-b950-2791faf798c2"),
    "rag_agent": UUID("fe26eac8-61c6-4158-a571-61fd680676c8"),
    "rag_agent_v2": UUID("e0f94ab3-fed2-4e43-a458-1d52464f4fc9"),
    "rag_agent_v3": UUID("f1a5b6c7-d8e9-4f0a-1b2c-3d4e5f6a7b8c"),
    "base_ai_agent": UUID("22292e7f-a3ba-4c63-a4c7-dd5c0c75cdaa"),
    "api_call_tool": UUID("674b8c1d-0cc6-4887-be92-e3a2906830ed"),
    "web_search_openai_agent": UUID("d6020df0-a7e0-4d82-b731-0a653beef2e6"),
    "web_search_openai_agent_v2": UUID("d6020df0-a7e0-4d82-b731-0a653beef2e5"),
    "sql_tool": UUID("f7ddbfcb-6843-4ae9-a15b-40aa565b955b"),
    "sql_db_service": UUID("4014e6bd-9d2d-4142-8bdc-6dd7d9068011"),
    "llm_call": UUID("7a039611-49b3-4bfd-b09b-c0f93edf3b79"),
    "snowflake_db_service": UUID("d27b7f18-b27d-48fb-b813-ac6c7eef49f2"),
    "hybrid_synthesizer": UUID("303ff9a5-3264-472c-b69f-c2da5be3bac8"),
    "hybrid_rag_agent": UUID("69ce9852-00cb-4c9d-86fe-8b8926afa994"),
    "relevant_chunk_selector": UUID("9870dd91-53fd-426b-aa99-7639da706f45"),
    "react_sql_agent": UUID("c0f1a2b3-4d5e-6f7a-8b9c-0d1e2f3a4b5c"),
    "react_sql_agent_v2": UUID("d0e83ab2-fed1-4e32-9347-0c41353f3eb8"),
    "run_sql_query_tool": UUID("667420c1-e2ca-446f-8e54-e0edd7e660bf"),
    "document_search": UUID("79399392-25ba-4cea-9f25-2738765dc329"),
    "document_enhanced_llm_call": UUID("6460b304-640c-4468-abd3-67bbff6902d4"),
    "document_react_loader_agent": UUID("1c2fdf5b-4a8d-4788-acb6-86b00124c7ce"),
    "ocr_call": UUID("a3b4c5d6-e7f8-9012-3456-789abcdef012"),
    "start": UUID("01357c0b-bc99-44ce-a435-995acc5e2544"),
    "start_v2": UUID("7a6e2c9b-5b1b-4a9b-9f2f-9b7f0540d4b0"),
    "filter": UUID("02468c0b-bc99-44ce-a435-995acc5e2545"),
    "gmail_sender": UUID("af96bb40-c9ea-4851-a663-f0e64363fcb2"),
    "python_code_runner": UUID("e2b00000-0000-1111-2222-333333333333"),
    "terminal_command_runner": UUID("e2b10000-1111-2222-3333-444444444444"),
    "linkup_search_tool": UUID("f3e45678-9abc-def0-1234-56789abcdef0"),
    "retriever_tool": UUID("2d8a4f3e-1c6b-4a9d-8f27-3e6b5a1c9d02"),
    "pdf_generation": UUID("428baac0-0c5f-4374-b2de-8075218082b4"),
    "project_reference": UUID("4c8f9e2d-1a3b-4567-8901-234567890abc"),
    "chunk_processor": UUID("5d9f0f3e-2b4c-5678-9012-345678901bcd"),
    "docx_generation": UUID("b5195a0f-94f5-4f5c-8804-32dd19b16833"),
    "static_responder": UUID("1F7334BE-7164-4440-BBF3-E986EED0388F"),
    "docx_template_agent": UUID("e2b30000-3333-4444-5555-666666666666"),
    "remote_mcp_tool": UUID("5e472b85-7601-4e5b-81c7-8b361b5c5c9a"),
    "table_lookup": UUID("4b5c6d7e-8f90-1234-5678-9abcdef01234"),
    "if_else": UUID("ce974746-4246-4300-828f-cf8553773616"),
}

DEFAULT_MODEL_WEB_SEARCH = "openai:gpt-5-mini"
DEFAULT_MODEL = "anthropic:claude-haiku-4-5"
DEFAULT_EMBEDDING_MODEL = "openai:text-embedding-3-large"
DEFAULT_OCR_MODEL = "mistral:mistral-ocr-latest"
ANTHROPIC_MODELS = [
    {"display_name": "Claude Haiku 4.5", "model_name": "claude-haiku-4-5"},
    {"display_name": "Claude Opus 4.5", "model_name": "claude-opus-4-5"},
    {"display_name": "Claude Sonnet 4.5", "model_name": "claude-sonnet-4-5"},
]


class ParameterLLMConfig(BaseModel):
    param_name: str
    param_id: UUID


def build_completion_service_config_definitions(
    component_version_id: UUID,
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
                    component_version_id=component_version_id,
                    name=COMPLETION_MODEL_IN_DB,
                    type=ParameterType.LLM_MODEL,
                    nullable=False,
                    default=DEFAULT_MODEL,
                    ui_component=UIComponent.SELECT,
                    ui_component_properties=UIComponentProperties(
                        label="Model Name",
                    ).model_dump(exclude_unset=True, exclude_none=True),
                    model_capabilities=[ModelCapabilityEnum.COMPLETION.value],
                )
            )
        if param.param_name == TEMPERATURE_IN_DB:
            definitions.append(
                db.ComponentParameterDefinition(
                    id=param.param_id,
                    component_version_id=component_version_id,
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
                    component_version_id=component_version_id,
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
                    component_version_id=component_version_id,
                    name=REASONING_IN_DB,
                    type=ParameterType.STRING,
                    nullable=True,
                    default=None,
                    ui_component=UIComponent.SELECT,
                    ui_component_properties=UIComponentProperties(
                        label="Reasoning",
                        options=[
                            SelectOption(value="low", label="Low"),
                            SelectOption(value="medium", label="Medium"),
                            SelectOption(value="high", label="High"),
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
                    component_version_id=component_version_id,
                    name="api_key",
                    type=ParameterType.LLM_API_KEY,
                    nullable=True,
                )
            )
    return definitions


def build_function_calling_service_config_definitions(
    component_version_id: UUID,
    params_to_seed: list[ParameterLLMConfig],
) -> list[db.ComponentParameterDefinition]:
    """
    Simple helper function to avoid code duplication.
    params_to_seed is a list of parameters to seed for the given component.
    options: [
        "completion_model",
        "temperature",
        "verbosity",
        "reasoning",
        "api_key",
    ]
    """
    definitions: list[db.ComponentParameterDefinition] = []
    for param in params_to_seed:
        if param.param_name == COMPLETION_MODEL_IN_DB:
            definitions.append(
                db.ComponentParameterDefinition(
                    id=param.param_id,
                    component_version_id=component_version_id,
                    name=COMPLETION_MODEL_IN_DB,
                    type=ParameterType.LLM_MODEL,
                    nullable=False,
                    default=DEFAULT_MODEL,
                    ui_component=UIComponent.SELECT,
                    ui_component_properties=UIComponentProperties(
                        label="Model Name",
                    ).model_dump(exclude_unset=True, exclude_none=True),
                    model_capabilities=[ModelCapabilityEnum.FUNCTION_CALLING.value],
                )
            )
        if param.param_name == TEMPERATURE_IN_DB:
            definitions.append(
                db.ComponentParameterDefinition(
                    id=param.param_id,
                    component_version_id=component_version_id,
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
                    component_version_id=component_version_id,
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
                    component_version_id=component_version_id,
                    name=REASONING_IN_DB,
                    type=ParameterType.STRING,
                    nullable=True,
                    default=None,
                    ui_component=UIComponent.SELECT,
                    ui_component_properties=UIComponentProperties(
                        label="Reasoning",
                        options=[
                            SelectOption(value="low", label="Low"),
                            SelectOption(value="medium", label="Medium"),
                            SelectOption(value="high", label="High"),
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
                    component_version_id=component_version_id,
                    name="api_key",
                    type=ParameterType.LLM_API_KEY,
                    nullable=True,
                )
            )
    return definitions


def build_embedding_service_config_definitions(
    component_version_id: UUID,
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
                    component_version_id=component_version_id,
                    name=EMBEDDING_MODEL_IN_DB,
                    type=ParameterType.LLM_MODEL,
                    nullable=False,
                    default=DEFAULT_EMBEDDING_MODEL,
                    ui_component=UIComponent.SELECT,
                    ui_component_properties=UIComponentProperties(
                        label="Embedding Model Name",
                    ).model_dump(exclude_unset=True, exclude_none=True),
                    model_capabilities=[ModelCapabilityEnum.EMBEDDING.value],
                )
            )
        if param.param_name == "api_key":
            definitions.append(
                db.ComponentParameterDefinition(
                    id=param.param_id,
                    component_version_id=component_version_id,
                    name="api_key",
                    type=ParameterType.STRING,
                    nullable=False,
                    default="",
                )
            )
    return definitions


def build_web_service_config_definitions(
    component_version_id: UUID,
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
                    component_version_id=component_version_id,
                    name=COMPLETION_MODEL_IN_DB,
                    type=ParameterType.LLM_MODEL,
                    nullable=False,
                    default=DEFAULT_MODEL_WEB_SEARCH,
                    ui_component=UIComponent.SELECT,
                    ui_component_properties=UIComponentProperties(
                        label="Model Name",
                    ).model_dump(exclude_unset=True, exclude_none=True),
                    model_capabilities=[ModelCapabilityEnum.WEB_SEARCH.value],
                )
            )
        if param.param_name == "api_key":
            definitions.append(
                db.ComponentParameterDefinition(
                    id=param.param_id,
                    component_version_id=component_version_id,
                    name="api_key",
                    type=ParameterType.LLM_API_KEY,
                    nullable=True,
                )
            )
    return definitions


def build_ocr_service_config_definitions(
    component_version_id: UUID,
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
                    component_version_id=component_version_id,
                    name=COMPLETION_MODEL_IN_DB,
                    type=ParameterType.LLM_MODEL,
                    nullable=False,
                    default=DEFAULT_OCR_MODEL,
                    ui_component=UIComponent.SELECT,
                    ui_component_properties=UIComponentProperties(
                        label="Model Name",
                    ).model_dump(exclude_unset=True, exclude_none=True),
                    model_capabilities=[ModelCapabilityEnum.OCR.value],
                )
            )
        if param.param_name == "api_key":
            definitions.append(
                db.ComponentParameterDefinition(
                    id=param.param_id,
                    component_version_id=component_version_id,
                    name="api_key",
                    type=ParameterType.LLM_API_KEY,
                    nullable=True,
                )
            )
    return definitions


def build_parameters_group(session: Session, parameter_groups: list[db.ParameterGroup]):
    for group in parameter_groups:
        existing_group = session.query(db.ParameterGroup).filter_by(id=group.id).first()
        if existing_group:
            existing_group.name = group.name
        else:
            session.add(group)

    session.flush()


def build_parameters_group_definitions(session: Session, component_parameter_groups: list[db.ComponentParameterGroup]):
    for component_parameter_group in component_parameter_groups:
        existing_cpg = (
            session.query(db.ComponentParameterGroup)
            .filter_by(
                component_version_id=component_parameter_group.component_version_id,
                parameter_group_id=component_parameter_group.parameter_group_id,
            )
            .first()
        )
        if existing_cpg:
            existing_cpg.group_order_within_component = component_parameter_group.group_order_within_component
        else:
            session.add(component_parameter_group)

    session.flush()  # Ensure relationships are saved before updating parameters


def build_components_parameters_assignments_to_parameter_groups(
    session: Session, parameter_group_assignments: dict[UUID, dict[str, int]]
):
    for param_id, group_info in parameter_group_assignments.items():
        param_def = session.query(db.ComponentParameterDefinition).filter_by(id=param_id).first()
        if param_def:
            param_def.parameter_group_id = group_info["parameter_group_id"]
            param_def.parameter_order_within_group = group_info["parameter_order_within_group"]


def seed_custom_llm_models(session: Session):
    if not settings.custom_models:
        LOGGER.warning("No custom models found in settings")
        return
    for provider, models in settings.custom_models["custom_models"].items():
        for model in models:
            if llm_model_exists_exact_match_service(
                session, model.get("model_name"), provider, model.get("model_capacity", [])
            ):
                LOGGER.warning(f"Model {model.get('model_name')} already exists")
                continue

            create_llm_model_service(
                session=session,
                llm_model_data=LLMModelCreate(
                    display_name=model.get("display_name"),
                    model_name=model.get("model_name"),
                    description=model.get("description"),
                    provider=provider,
                    model_capacity=model.get("model_capacity", []),
                ),
            )


def seed_anthropic_models(session: Session):
    for model in ANTHROPIC_MODELS:
        if llm_model_exists_exact_match_service(
            session,
            model.get("model_name"),
            "anthropic",
            [
                ModelCapabilityEnum.COMPLETION.value,
                ModelCapabilityEnum.FUNCTION_CALLING.value,
                ModelCapabilityEnum.IMAGE.value,
                ModelCapabilityEnum.CONSTRAINED_OUTPUT.value,
            ],
        ):
            LOGGER.warning(f"Model {model.get('model_name')} already exists")
            continue
        LOGGER.info(f"Creating model {model.get('model_name')}")
        create_llm_model_service(
            session=session,
            llm_model_data=LLMModelCreate(
                display_name=model.get("display_name"),
                model_name=model.get("model_name"),
                description="",
                provider="anthropic",
                model_capacity=[
                    ModelCapabilityEnum.COMPLETION.value,
                    ModelCapabilityEnum.FUNCTION_CALLING.value,
                    ModelCapabilityEnum.IMAGE.value,
                    ModelCapabilityEnum.CONSTRAINED_OUTPUT.value,
                ],
            ),
        )
