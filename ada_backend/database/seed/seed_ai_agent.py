import json
from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.database import models as db
from ada_backend.database.component_definition_seeding import (
    upsert_component_categories,
    upsert_component_versions,
    upsert_components,
    upsert_components_parameter_definitions,
    upsert_release_stage_to_current_version_mapping,
)
from ada_backend.database.models import (
    ParameterType,
    UIComponent,
    UIComponentProperties,
)
from ada_backend.database.seed.constants import (
    COMPLETION_MODEL_IN_DB,
    TEMPERATURE_IN_DB,
)
from ada_backend.database.seed.seed_categories import CATEGORY_UUIDS
from ada_backend.database.seed.seed_tool_description import TOOL_DESCRIPTION_UUIDS
from ada_backend.database.seed.utils import (
    COMPONENT_UUIDS,
    COMPONENT_VERSION_UUIDS,
    ParameterLLMConfig,
    build_function_calling_service_config_definitions,
)

SYSTEM_PROMPT_PARAMETER_DEF_ID = UUID("1cd1cd58-f066-4cf5-a0f5-9b2018fc4c6a")
SYSTEM_PROMPT_PARAMETER_NAME = "initial_prompt"
AGENT_TOOLS_PARAMETER_NAME = "agent_tools"
AI_MODEL_PARAMETER_IDS = {
    "output_format": UUID("e5282ccb-dcaa-4970-93c1-f6ef5018492d"),
    "max_iterations": UUID("89efb2e1-9228-44db-91d6-871a41042067"),
    TEMPERATURE_IN_DB: UUID("5bdece0d-bbc1-4cc7-a192-c4b7298dc163"),
    "date_in_system_prompt": UUID("f7dbbe12-e6ff-5bfe-b006-f6bf0e9cbf4d"),
    "allow_tool_shortcuts": UUID("3f8aa317-215a-4075-80ba-efca2a3d83ca"),
    "input_data_field_for_messages_history": UUID("bf56e90a-5e2b-4777-9ef4-34838b8973b6"),
    "first_history_messages": UUID("4ca78b43-4484-4a9d-bdab-e6dbdaff6da1"),
    COMPLETION_MODEL_IN_DB: UUID("e2d157b4-f26d-41b4-9e47-62b5b041a9ff"),
    "last_history_messages": UUID("e6caae01-d5ee-4afd-a995-e5ae9dbf3fbc"),
}

# Parameter Group UUIDs
PARAMETER_GROUP_UUIDS = {
    "agent_behavior_settings": UUID("b2c3d4e5-f6a7-8901-bcde-f12345678901"),
    "history_management": UUID("c3d4e5f6-a7b8-9012-cdef-123456789012"),
}


def seed_ai_agent_components(session: Session):
    base_ai_agent_component = db.Component(
        id=COMPONENT_UUIDS["base_ai_agent"],
        name="AI Agent",
        base_component="AI Agent",
        is_agent=True,
        function_callable=True,
        can_use_function_calling=True,
        icon="tabler-robot",
    )
    upsert_components(
        session=session,
        components=[
            base_ai_agent_component,
        ],
    )
    base_ai_agent_version = db.ComponentVersion(
        id=COMPONENT_VERSION_UUIDS["base_ai_agent"],
        component_id=COMPONENT_UUIDS["base_ai_agent"],
        version_tag="0.0.1",
        release_stage=db.ReleaseStage.PUBLIC,
        default_tool_description_id=TOOL_DESCRIPTION_UUIDS["default_ai_agent_description"],
        description=(
            "AI operator provided with tools."
            " LLM calls will choose next action step by step until it decides to provide a response."
        ),
    )
    upsert_component_versions(
        session=session,
        component_versions=[base_ai_agent_version],
    )
    upsert_components_parameter_definitions(
        session=session,
        component_parameter_definitions=[
            # React Agent
            db.ComponentParameterDefinition(
                id=UUID("521cfedb-e3f1-4953-9372-1c6a0cfdba6f"),
                component_version_id=base_ai_agent_version.id,
                name=AGENT_TOOLS_PARAMETER_NAME,
                type=ParameterType.TOOL,
                nullable=False,
                is_advanced=False,
            ),
            db.ComponentParameterDefinition(
                id=AI_MODEL_PARAMETER_IDS["allow_tool_shortcuts"],
                component_version_id=base_ai_agent_version.id,
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
                id=AI_MODEL_PARAMETER_IDS["max_iterations"],
                component_version_id=base_ai_agent_version.id,
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
                id=SYSTEM_PROMPT_PARAMETER_DEF_ID,
                component_version_id=base_ai_agent_version.id,
                name=SYSTEM_PROMPT_PARAMETER_NAME,
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
                id=AI_MODEL_PARAMETER_IDS["input_data_field_for_messages_history"],
                component_version_id=base_ai_agent_version.id,
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
                id=AI_MODEL_PARAMETER_IDS["first_history_messages"],
                component_version_id=base_ai_agent_version.id,
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
                id=AI_MODEL_PARAMETER_IDS["last_history_messages"],
                component_version_id=base_ai_agent_version.id,
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
            db.ComponentParameterDefinition(
                id=AI_MODEL_PARAMETER_IDS["date_in_system_prompt"],
                component_version_id=base_ai_agent_version.id,
                name="date_in_system_prompt",
                type=ParameterType.BOOLEAN,
                nullable=False,
                default="False",
                ui_component=UIComponent.CHECKBOX,
                ui_component_properties=UIComponentProperties(
                    label="Include current date in system prompt",
                    description=(
                        "When enabled, the current date and time will be automatically added to the"
                        " beginning of the system prompt."
                        " This can help the AI agent be aware of the current date for time-sensitive tasks."
                    ),
                ).model_dump(exclude_unset=True, exclude_none=True),
                is_advanced=True,
            ),
            db.ComponentParameterDefinition(
                id=UUID("e5282ccb-dcaa-4970-93c1-f6ef5018492d"),
                component_version_id=base_ai_agent_version.id,
                name="output_format",
                type=ParameterType.STRING,
                nullable=True,
                default=None,
                ui_component=UIComponent.TEXTAREA,
                ui_component_properties=UIComponentProperties(
                    label="Output Format",
                    placeholder=json.dumps(
                        {
                            "answer": {"type": "string", "description": "The imposed format of the agent's answer."},
                            "is_ending_conversation": {
                                "type": "boolean",
                                "description": "Boolean detecting if the conversation is over or not",
                            },
                        },
                        indent=4,
                    ),
                    description=(
                        "JSON schema defining the properties/parameters of the output tool. "
                        'Example: {"answer": {"type": "string", "description": "The answer content"}, '
                        '"is_ending_conversation": {"type": "boolean", "description": "End conversation?"}}'
                    ),
                ).model_dump(exclude_unset=True, exclude_none=True),
                is_advanced=True,
            ),
            *build_function_calling_service_config_definitions(
                component_version_id=base_ai_agent_version.id,
                params_to_seed=[
                    ParameterLLMConfig(
                        param_name=COMPLETION_MODEL_IN_DB,
                        param_id=AI_MODEL_PARAMETER_IDS[COMPLETION_MODEL_IN_DB],
                    ),
                    ParameterLLMConfig(
                        param_name="api_key",
                        param_id=UUID("78d5d921-9501-44b3-9939-7d7ebf063513"),
                    ),
                    ParameterLLMConfig(
                        param_name=TEMPERATURE_IN_DB,
                        param_id=AI_MODEL_PARAMETER_IDS[TEMPERATURE_IN_DB],
                    ),
                ],
            ),
        ],
    )

    # Create release stage mapping
    upsert_release_stage_to_current_version_mapping(
        session=session,
        component_id=base_ai_agent_version.component_id,
        release_stage=base_ai_agent_version.release_stage,
        component_version_id=base_ai_agent_version.id,
    )
    upsert_component_categories(
        session=session,
        component_id=base_ai_agent_component.id,
        category_ids=[CATEGORY_UUIDS["most_used"]],
    )


def seed_ai_agent_parameter_groups(session: Session):
    """Seed parameter groups for AI Agent component."""

    # Create parameter groups
    parameter_groups = [
        db.ParameterGroup(id=PARAMETER_GROUP_UUIDS["agent_behavior_settings"], name="Agent behavior settings"),
        db.ParameterGroup(id=PARAMETER_GROUP_UUIDS["history_management"], name="Management of conversation history"),
    ]

    # Upsert parameter groups
    for group in parameter_groups:
        existing_group = session.query(db.ParameterGroup).filter_by(id=group.id).first()
        if existing_group:
            existing_group.name = group.name
        else:
            session.add(group)

    session.flush()  # Ensure groups are saved before creating relationships

    # Create component version-parameter group relationships
    component_parameter_groups = [
        db.ComponentParameterGroup(
            component_version_id=COMPONENT_UUIDS["base_ai_agent"],
            parameter_group_id=PARAMETER_GROUP_UUIDS["agent_behavior_settings"],
            group_order_within_component=1,
        ),
        db.ComponentParameterGroup(
            component_version_id=COMPONENT_UUIDS["base_ai_agent"],
            parameter_group_id=PARAMETER_GROUP_UUIDS["history_management"],
            group_order_within_component=2,
        ),
    ]

    # Upsert component parameter groups
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

    # Update existing parameter definitions to link them to groups
    parameter_group_assignments = {
        # Agent behavior settings Group
        AI_MODEL_PARAMETER_IDS["output_format"]: {
            "parameter_group_id": PARAMETER_GROUP_UUIDS["agent_behavior_settings"],
            "parameter_order_within_group": 1,
        },
        AI_MODEL_PARAMETER_IDS["allow_tool_shortcuts"]: {
            "parameter_group_id": PARAMETER_GROUP_UUIDS["agent_behavior_settings"],
            "parameter_order_within_group": 2,
        },
        AI_MODEL_PARAMETER_IDS["max_iterations"]: {
            "parameter_group_id": PARAMETER_GROUP_UUIDS["agent_behavior_settings"],
            "parameter_order_within_group": 3,
        },
        AI_MODEL_PARAMETER_IDS[TEMPERATURE_IN_DB]: {
            "parameter_group_id": PARAMETER_GROUP_UUIDS["agent_behavior_settings"],
            "parameter_order_within_group": 4,
        },
        # History Management Group
        AI_MODEL_PARAMETER_IDS["input_data_field_for_messages_history"]: {
            "parameter_group_id": PARAMETER_GROUP_UUIDS["history_management"],
            "parameter_order_within_group": 1,
        },
        AI_MODEL_PARAMETER_IDS["first_history_messages"]: {
            "parameter_group_id": PARAMETER_GROUP_UUIDS["history_management"],
            "parameter_order_within_group": 2,
        },
        AI_MODEL_PARAMETER_IDS["last_history_messages"]: {
            "parameter_group_id": PARAMETER_GROUP_UUIDS["history_management"],
            "parameter_order_within_group": 3,
        },
        AI_MODEL_PARAMETER_IDS["date_in_system_prompt"]: {
            "parameter_group_id": PARAMETER_GROUP_UUIDS["history_management"],
            "parameter_order_within_group": 4,
        },
    }

    # Update parameter definitions with group assignments
    for param_id, group_info in parameter_group_assignments.items():
        param_def = session.query(db.ComponentParameterDefinition).filter_by(id=param_id).first()
        if param_def:
            param_def.parameter_group_id = group_info["parameter_group_id"]
            param_def.parameter_order_within_group = group_info["parameter_order_within_group"]

    session.commit()
