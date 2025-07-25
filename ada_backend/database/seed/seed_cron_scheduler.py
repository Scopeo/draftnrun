from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.database import models as db
from ada_backend.database.models import (
    ParameterType,
    UIComponent,
    UIComponentProperties,
    SelectOption,
)
from ada_backend.database.component_definition_seeding import (
    upsert_components,
    upsert_components_parameter_definitions,
)
from ada_backend.database.seed.utils import COMPONENT_UUIDS
from ada_backend.database.seed.seed_tool_description import TOOL_DESCRIPTION_UUIDS
from engine.agent.triggers.utils import get_timezone_options


def seed_cron_scheduler_components(session: Session):
    """
    Seed the CRON_SCHEDULER component with its parameter definitions.
    """

    # Import timezone options from the component's utils

    timezone_options_dict = get_timezone_options()

    # Flatten the timezone options into a single list for the database
    timezone_options = []
    for _, options in timezone_options_dict.items():
        for option in options:
            timezone_options.append(SelectOption(value=option["value"], label=option["label"]))

    # Create the CRON_SCHEDULER component
    cron_scheduler = db.Component(
        id=COMPONENT_UUIDS["cron_scheduler"],
        name="Cron Scheduler",  # Must match SupportedEntityType.CRON_SCHEDULER
        description="Schedules workflow execution based on cron expressions. Triggers the workflow "
                    "automatically at specified times.",
        is_agent=True,
        function_callable=False,
        can_use_function_calling=False,
        release_stage=db.ReleaseStage.PUBLIC,
        default_tool_description_id=TOOL_DESCRIPTION_UUIDS["cron_scheduler_tool_description"],
    )

    upsert_components(
        session=session,
        components=[cron_scheduler],
    )

    # Parameter definitions for CRON_SCHEDULER
    cron_expression_param = db.ComponentParameterDefinition(
        id=UUID("c20a1001-c001-4001-a001-c40a1001c001"),
        component_id=cron_scheduler.id,
        name="cron_expression",
        type=ParameterType.STRING,
        nullable=False,
        default="0 9 * * *",  # Daily at 9 AM
        ui_component=UIComponent.TEXTFIELD,
        ui_component_properties=UIComponentProperties(
            label="Cron Expression", placeholder="0 9 * * *", description="Format: minute hour day month day_of_week"
        ).model_dump(exclude_unset=True, exclude_none=True),
        order=1,
    )

    timezone_param = db.ComponentParameterDefinition(
        id=UUID("c20a1001-c002-4002-a002-c40a1001c002"),
        component_id=cron_scheduler.id,
        name="timezone",
        type=ParameterType.STRING,
        nullable=False,
        default="UTC",
        ui_component=UIComponent.SELECT,
        ui_component_properties=UIComponentProperties(
            label="Timezone",
            options=timezone_options,
            description="Choose your timezone to ensure schedules run at the correct local time",
        ).model_dump(exclude_unset=True, exclude_none=True),
        order=2,
    )

    enabled_param = db.ComponentParameterDefinition(
        id=UUID("c20a1001-c003-4003-a003-c40a1001c003"),
        component_id=cron_scheduler.id,
        name="enabled",
        type=ParameterType.BOOLEAN,
        nullable=False,
        default="true",  # Enabled by default as requested
        ui_component=UIComponent.CHECKBOX,
        ui_component_properties=UIComponentProperties(
            label="Enable deployment in production",
            description="Check this box to enable automatic deployment in production",
        ).model_dump(exclude_unset=True, exclude_none=True),
        order=3,
    )

    upsert_components_parameter_definitions(
        session=session,
        component_parameter_definitions=[
            cron_expression_param,
            timezone_param,
            enabled_param,
        ],
    )
