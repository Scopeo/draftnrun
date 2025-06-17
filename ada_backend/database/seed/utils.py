from uuid import UUID

from pydantic import BaseModel

from ada_backend.database.models import ParameterType, SelectOption, UIComponent, UIComponentProperties
from ada_backend.database import models as db
from ada_backend.services.registry import PARAM_MODEL_NAME_IN_DB


# Define UUIDs for components and instances
COMPONENT_UUIDS: dict[str, UUID] = {
    "synthesizer": UUID("6f790dd1-06f6-4489-a655-1a618763a114"),
    "retriever": UUID("8baf68a9-1671-4ed5-8374-6ec218f5d9a6"),
    "cohere_reranker": UUID("dfdc8b87-610f-4ce0-8cf1-276e80bec32b"),
    "vocabulary_search": UUID("323cfc43-76d9-4ae1-b950-2791faf798c2"),
    "vocabulary_enhanced_synthesizer": UUID("954856e7-bfaa-485a-a053-d4b9b9cf6804"),
    "formatter": UUID("079512c6-28e2-455f-af2c-f196015534bd"),
    "vocabulary_enhanced_rag_agent": UUID("d203d691-1245-49c9-a881-c4be8d79d30a"),
    "rag_agent": UUID("fe26eac8-61c6-4158-a571-61fd680676c8"),
    "base_ai_agent": UUID("22292e7f-a3ba-4c63-a4c7-dd5c0c75cdaa"),
    "api_call_tool": UUID("674b8c1d-0cc6-4887-be92-e3a2906830ed"),
    "tavily_agent": UUID("449f8f59-7aff-4b2d-b244-d2fcc09f6651"),
    "web_search_openai_agent": UUID("d6020df0-a7e0-4d82-b731-0a653beef2e6"),
    "switch_categorical_pipeline": UUID("064df1da-2151-4bce-adab-0ab6d06cf6cb"),
    "sequential_pipeline": UUID("d2991b15-bd9f-4939-a0e9-7fc434f20b3d"),
    "static_responder": UUID("94d56d5a-baf3-4f60-864d-fb062ba00357"),
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
    "input": UUID("01357c0b-bc99-44ce-a435-995acc5e2544"),
}


class ParameterLLMConfig(BaseModel):
    param_name: str
    param_id: UUID


def build_llm_config_definitions(
    component_id: UUID,
    params_to_seed: list[ParameterLLMConfig],
) -> list[db.ComponentParameterDefinition]:
    """
    Simple helper function to avoid code duplication.
    params_to_seed is a list of parameters to seed for the given component.
    options: [
        "model_name",
        "embedding_model_name",
        "default_temperature",
        "model_speech_to_text",
        "model_config_text_to_speech",
        "api_key",
    ]
    """
    definitions: list[db.ComponentParameterDefinition] = []
    for param in params_to_seed:
        if param.param_name == PARAM_MODEL_NAME_IN_DB:
            definitions.append(
                db.ComponentParameterDefinition(
                    id=param.param_id,
                    component_id=component_id,
                    name=PARAM_MODEL_NAME_IN_DB,
                    type=ParameterType.STRING,
                    nullable=False,
                    default="openai:gpt-4.1-mini",
                    ui_component=UIComponent.SELECT,
                    ui_component_properties=UIComponentProperties(
                        options=[
                            # OpenAI
                            SelectOption(value="openai:gpt-4.1", label="GPT-4.1"),
                            SelectOption(value="openai:gpt-4.1-mini", label="GPT-4.1 Mini"),
                            SelectOption(value="openai:gpt-4.1-nano", label="GPT-4.1 Nano"),
                            SelectOption(value="openai:gpt-4o", label="GPT-4o"),
                            SelectOption(value="openai:gpt-4o-mini", label="GPT-4o Mini"),
                            SelectOption(value="openai:o4-mini-2025-04-16", label="GPT-4o4 Mini"),
                            SelectOption(value="openai:o3-2025-04-16", label="GPT-4o3"),
                            # TODO: Add models once they work using llm_service
                            # Google (Gemini)
                            # SelectOption(value="google:gemini-2.5-pro-preview-06-05", label="Gemini 2.5 Pro"),
                            # SelectOption(value="google:gemini-2.5-flash-preview-05-20", label="Gemini 2.5 Flash"),
                            # SelectOption(value="google:gemini-2.0-flash", label="Gemini 2.0 Flash"),
                            # SelectOption(value="google:gemini-2.0-flash-lite", label="Gemini 2.0 Flash lite"),
                            # Mistral
                            # SelectOption(value="mistral:mistral-large", label="Mistral Large"),
                            # SelectOption(value="mistral:mistral-small-3", label="Mistral Small 3"),
                            # # Anthropic (Claude) TODO: Add Anthropic (Claude)
                            # SelectOption(value="anthropic:claude-3.7-sonnet", label="Claude 3.7 Sonnet"),
                            # SelectOption(value="anthropic:claude-3.5-sonnet", label="Claude 3.5 Sonnet"),
                            # SelectOption(value="anthropic:claude-3.5-haiku", label="Claude 3.5 Haiku"),
                        ],
                        label="Model Name",
                    ).model_dump(exclude_unset=True, exclude_none=True),
                )
            )
        if param.param_name == "web_search_model_name":
            definitions.append(
                db.ComponentParameterDefinition(
                    id=param.param_id,
                    component_id=component_id,
                    name=PARAM_MODEL_NAME_IN_DB,
                    type=ParameterType.STRING,
                    nullable=False,
                    default="openai:gpt-4.1-mini",
                    ui_component=UIComponent.SELECT,
                    ui_component_properties=UIComponentProperties(
                        options=[
                            # OpenAI
                            SelectOption(value="openai:gpt-4.1", label="GPT-4.1"),
                            SelectOption(value="openai:gpt-4.1-mini", label="GPT-4.1 Mini"),
                            SelectOption(value="openai:gpt-4o", label="GPT-4o"),
                            SelectOption(value="openai:gpt-4o-mini", label="GPT-4o Mini"),
                            SelectOption(value="openai:o4-mini-2025-04-16", label="GPT-4o4-mini"),
                            SelectOption(value="openai:o3-2025-04-16", label="GPT-4o3"),
                        ],
                        label="Web Search Model Name",
                    ).model_dump(exclude_unset=True, exclude_none=True),
                )
            )
        if param.param_name == "embedding_model_name":
            definitions.append(
                db.ComponentParameterDefinition(
                    id=param.param_id,
                    component_id=component_id,
                    name="embedding_model_name",
                    type=ParameterType.STRING,
                    nullable=False,
                    default="openai:text-embedding-3-large",
                    ui_component=UIComponent.SELECT,
                    ui_component_properties=UIComponentProperties(
                        options=[
                            # OpenAI
                            SelectOption(value="openai:text-embedding-3-large", label="Text Embedding 3 Large"),
                            # Google (Gemini)
                            SelectOption(
                                value="google:gemini-embedding-exp-03-07", label="Gemini Embedding exp-03-07"
                            ),
                            # Mistral
                            SelectOption(value="mistral:mistral-embed", label="Mistral Embed"),
                        ],
                        label="Embedding Model Name",
                    ).model_dump(exclude_unset=True, exclude_none=True),
                )
            )
        if param.param_name == "default_temperature":
            definitions.append(
                db.ComponentParameterDefinition(
                    id=param.param_id,
                    component_id=component_id,
                    name="default_temperature",
                    type=ParameterType.FLOAT,
                    nullable=False,
                    default="0.3",
                )
            )
        if param.param_name == "model_speech_to_text":
            definitions.append(
                db.ComponentParameterDefinition(
                    id=param.param_id,
                    component_id=component_id,
                    name="model_speech_to_text",
                    type=ParameterType.STRING,
                    nullable=False,
                    default="openai:gpt-4o-mini-transcribe",
                    ui_component=UIComponent.SELECT,
                    ui_component_properties=UIComponentProperties(
                        options=[
                            # OpenAI
                            SelectOption(value="openai:gpt-4o-transcribe", label="GPT-4o Transcribe"),
                            SelectOption(value="openai:gpt-4o-mini-transcribe", label="GPT-4o Mini Transcribe"),
                        ],
                        label="Model Speech To Text",
                    ).model_dump(exclude_unset=True, exclude_none=True),
                )
            )
        # TODO: Add ui_component_properties
        if param.param_name == "model_config_text_to_speech":
            definitions.append(
                db.ComponentParameterDefinition(
                    id=param.param_id,
                    component_id=component_id,
                    name="model_config_text_to_speech",
                    type=ParameterType.JSON,
                    nullable=False,
                    default="openai:gpt-4o-mini-tts",
                    ui_component=UIComponent.SELECT,
                    ui_component_properties=UIComponentProperties(
                        options=[
                            # OpenAI
                            SelectOption(value="openai:gpt-4o-mini-tts", label="GPT-4o Mini TTS"),
                            SelectOption(value="openai:gpt-4o-tts", label="GPT-4o TTS"),
                            # Google
                            SelectOption(value="google:chirp-3-hd", label="Chirp 3 HD"),
                        ],
                        label="Model Text To Speech",
                    ),
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
