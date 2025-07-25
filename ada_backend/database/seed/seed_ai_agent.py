from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.database import models as db
from ada_backend.database.models import (
    ParameterType,
    UIComponent,
    UIComponentProperties,
)
from ada_backend.database.component_definition_seeding import (
    upsert_components,
    upsert_components_parameter_definitions,
)
from ada_backend.database.seed.seed_tool_description import TOOL_DESCRIPTION_UUIDS
from ada_backend.database.seed.utils import (
    COMPONENT_UUIDS,
    ParameterLLMConfig,
    build_function_calling_service_config_definitions,
)
from ada_backend.services.registry import COMPLETION_MODEL_IN_DB


def seed_ai_agent_components(session: Session):
    base_ai_agent = db.Component(
        id=COMPONENT_UUIDS["base_ai_agent"],
        name="AI Agent",
        description=(
            "AI operator provided with tools."
            " LLM calls will choose next action step by step until it decides to provide a response."
        ),
        is_agent=True,
        function_callable=True,
        can_use_function_calling=True,
        release_stage=db.ReleaseStage.PUBLIC,
        default_tool_description_id=TOOL_DESCRIPTION_UUIDS["default_ai_agent_description"],
    )
    upsert_components(
        session=session,
        components=[
            base_ai_agent,
        ],
    )
    upsert_components_parameter_definitions(
        session=session,
        component_parameter_definitions=[
            # React Agent
            db.ComponentParameterDefinition(
                id=UUID("521cfedb-e3f1-4953-9372-1c6a0cfdba6f"),
                component_id=base_ai_agent.id,
                name="agent_tools",
                type=ParameterType.TOOL,
                nullable=False,
                is_advanced=False,
            ),
            db.ComponentParameterDefinition(
                id=UUID("3f8aa317-215a-4075-80ba-efca2a3d83ca"),
                component_id=base_ai_agent.id,
                name="allow_tool_shortcuts",
                type=ParameterType.BOOLEAN,
                nullable=False,
                default="False",
                ui_component=UIComponent.CHECKBOX,
                ui_component_properties=UIComponentProperties(
                    label="Allow tools to answer directly without asking the agent to process results."
                ).model_dump(exclude_unset=True, exclude_none=True),
                is_advanced=True,
            ),
            db.ComponentParameterDefinition(
                id=UUID("89efb2e1-9228-44db-91d6-871a41042067"),
                component_id=base_ai_agent.id,
                name="max_iterations",
                type=ParameterType.INTEGER,
                nullable=True,
                default="10",
                ui_component=UIComponent.SLIDER,
                ui_component_properties=UIComponentProperties(
                    min=1, max=50, step=1, marks=True, label="Maximum Iterations"
                ).model_dump(exclude_unset=True, exclude_none=True),
                is_advanced=True,
            ),
            db.ComponentParameterDefinition(
                id=UUID("1cd1cd58-f066-4cf5-a0f5-9b2018fc4c6a"),
                component_id=base_ai_agent.id,
                name="initial_prompt",
                type=ParameterType.STRING,
                nullable=True,
                default=(
                    "Act as a helpful assistant. "
                    "You can use tools to answer questions,"
                    " but you can also answer directly if you have enough information."
                ),
                ui_component=UIComponent.TEXTAREA,
                ui_component_properties=UIComponentProperties(
                    label="System Prompt",
                    description=(
                        "This prompt will be used to initialize the agent and set its behavior."
                        " It can be used to provide context or instructions for the agent."
                        " It will be used as the first message of the conversation in the agent's memory."
                        " You can use it to set the agent's personality, role,"
                        "or to provide specific instructions on how to handle certain types of questions."
                        " The conversation you have with the agent (or your single message)"
                        " is going to be added after this first message."
                    ),
                ).model_dump(exclude_unset=True, exclude_none=True),
            ),
            db.ComponentParameterDefinition(
                id=UUID("bf56e90a-5e2b-4777-9ef4-34838b8973b6"),
                component_id=base_ai_agent.id,
                name="input_data_field_for_messages_history",
                type=ParameterType.STRING,
                nullable=False,
                default="messages",
                ui_component=UIComponent.TEXTAREA,
                ui_component_properties=UIComponentProperties(
                    label="Messages history key from input",
                    placeholder="Enter the key from your input data to access messages history",
                ).model_dump(exclude_unset=True, exclude_none=True),
                is_advanced=True,
            ),
            db.ComponentParameterDefinition(
                id=UUID("4ca78b43-4484-4a9d-bdab-e6dbdaff6da1"),
                component_id=base_ai_agent.id,
                name="first_history_messages",
                type=ParameterType.INTEGER,
                nullable=True,
                default="1",
                ui_component=UIComponent.SLIDER,
                ui_component_properties=UIComponentProperties(
                    min=1,
                    max=50,
                    step=1,
                    marks=True,
                    label="Conversation start",
                    description=(
                        "The number of messages to keep in memory from the beginning of the conversation.\n"
                        "To avoid to big conversations, that causes performance loss, we advice not"
                        " to keep too many messages in the memory.\n"
                        "This parameter sets the number of messages to keep in memory at the beginning"
                        " of the conversation (including the system prompt)."
                    ),
                ).model_dump(exclude_unset=True, exclude_none=True),
                is_advanced=True,
            ),
            db.ComponentParameterDefinition(
                id=UUID("e6caae01-d5ee-4afd-a995-e5ae9dbf3fbc"),
                component_id=base_ai_agent.id,
                name="last_history_messages",
                type=ParameterType.INTEGER,
                nullable=True,
                default="50",
                ui_component=UIComponent.SLIDER,
                ui_component_properties=UIComponentProperties(
                    min=2,
                    max=100,
                    step=1,
                    marks=True,
                    label="Conversation end",
                    description=(
                        "The number of messages to keep in memory from the end of the conversation.\n"
                        "To avoid to big conversations, that causes performance loss, we advice not"
                        " to keep too many messages in the memory.\n"
                        "This parameter sets the number of messages to keep in memory at the end"
                        " of the conversation."
                    ),
                ).model_dump(exclude_unset=True, exclude_none=True),
                is_advanced=True,
            ),
            *build_function_calling_service_config_definitions(
                component_id=base_ai_agent.id,
                params_to_seed=[
                    ParameterLLMConfig(
                        param_name=COMPLETION_MODEL_IN_DB,
                        param_id=UUID("e2d157b4-f26d-41b4-9e47-62b5b041a9ff"),
                    ),
                    ParameterLLMConfig(
                        param_name="api_key",
                        param_id=UUID("78d5d921-9501-44b3-9939-7d7ebf063513"),
                    ),
                ],
            ),
        ],
    )
