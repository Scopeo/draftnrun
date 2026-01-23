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
from ada_backend.database.seed.seed_categories import CATEGORY_UUIDS
from ada_backend.database.seed.seed_tool_description import TOOL_DESCRIPTION_UUIDS
from ada_backend.database.seed.utils import (
    COMPONENT_UUIDS,
    COMPONENT_VERSION_UUIDS,
)
from engine.components.if_else import IfElseOperator

# Single source of truth for operator metadata
OPERATOR_METADATA = [
    # Unary operators
    {"value": IfElseOperator.IS_EMPTY.value, "label": "Is empty", "requires_value_b": False},
    {"value": IfElseOperator.IS_NOT_EMPTY.value, "label": "Is not empty", "requires_value_b": False},
    # Number operators
    {"value": IfElseOperator.NUMBER_GREATER_THAN.value, "label": "[Number] Is greater than", "requires_value_b": True},
    {"value": IfElseOperator.NUMBER_LESS_THAN.value, "label": "[Number] Is less than", "requires_value_b": True},
    {"value": IfElseOperator.NUMBER_EQUAL_TO.value, "label": "[Number] Is equal to", "requires_value_b": True},
    {
        "value": IfElseOperator.NUMBER_GREATER_OR_EQUAL.value,
        "label": "[Number] Is greater than or equal to",
        "requires_value_b": True,
    },
    {
        "value": IfElseOperator.NUMBER_LESS_OR_EQUAL.value,
        "label": "[Number] Is less than or equal to",
        "requires_value_b": True,
    },
    # Boolean operators
    {"value": IfElseOperator.BOOLEAN_IS_TRUE.value, "label": "[Boolean] Is true", "requires_value_b": False},
    {"value": IfElseOperator.BOOLEAN_IS_FALSE.value, "label": "[Boolean] Is false", "requires_value_b": False},
    # Text operators
    {"value": IfElseOperator.TEXT_CONTAINS.value, "label": "[Text] Contains", "requires_value_b": True},
    {
        "value": IfElseOperator.TEXT_DOES_NOT_CONTAIN.value,
        "label": "[Text] Does not contain",
        "requires_value_b": True,
    },
    {"value": IfElseOperator.TEXT_EQUALS.value, "label": "[Text] Equals", "requires_value_b": True},
    {"value": IfElseOperator.TEXT_DOES_NOT_EQUAL.value, "label": "[Text] Does not equal", "requires_value_b": True},
]


def seed_if_else_components(session: Session):
    if_else = db.Component(
        id=COMPONENT_UUIDS["if_else"],
        name="If/Else",
        is_agent=True,
        function_callable=True,
        is_protected=True,
        icon="tabler-git-branch",
    )
    upsert_components(
        session=session,
        components=[
            if_else,
        ],
    )
    if_else_version = db.ComponentVersion(
        id=COMPONENT_VERSION_UUIDS["if_else"],
        component_id=COMPONENT_UUIDS["if_else"],
        version_tag="0.0.1",
        release_stage=db.ReleaseStage.BETA,
        description=(
            "A conditional component that controls workflow execution by evaluating multiple conditions "
            "with AND/OR logic. "
            "If the conditions evaluate to true, downstream nodes continue. If false, downstream execution is halted."
        ),
        default_tool_description_id=TOOL_DESCRIPTION_UUIDS["default_if_else_tool_description"],
    )
    upsert_component_versions(
        session=session,
        component_versions=[if_else_version],
    )

    upsert_components_parameter_definitions(
        session=session,
        component_parameter_definitions=[
            db.ComponentParameterDefinition(
                id=UUID("b2c3d4e5-f6a7-8901-2345-678901234567"),
                component_version_id=if_else_version.id,
                name="conditions",
                type=ParameterType.JSON,
                nullable=False,
                default=[
                    {
                        "value_a": "",
                        "operator": "number_equal_to",
                        "value_b": "",
                        "next_logic": None,
                    }
                ],
                ui_component=UIComponent.CONDITION_BUILDER,
                ui_component_properties=UIComponentProperties(
                    label="Conditions",
                    description=("Define conditions with AND/OR logic."),
                    placeholder=(
                        '[{"value_a": "@{{instance_id.output}}", "operator": "number_greater_than", "value_b": '
                        '10, "next_logic": "AND"}]'
                    ),
                    available_operators=OPERATOR_METADATA,
                ).model_dump(exclude_unset=True, exclude_none=True),
            ),
        ],
    )
    upsert_component_categories(
        session=session,
        component_id=if_else.id,
        category_ids=[CATEGORY_UUIDS["workflow_logic"]],
    )

    upsert_release_stage_to_current_version_mapping(
        session=session,
        component_id=if_else.id,
        release_stage=if_else_version.release_stage,
        component_version_id=if_else_version.id,
    )
