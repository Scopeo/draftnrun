"""
Regression tests for create_or_update_component_instance in update_pipeline_service.

When cloning a component instance that has a non-nullable parameter with a default
value but no stored row in basic_parameters, the copy path passes value=None.
The fix falls back to param_def.default instead of raising ValueError.

Integration tests that run against the real seeded database.
"""

from ada_backend.database.seed.utils import COMPONENT_UUIDS, COMPONENT_VERSION_UUIDS
from ada_backend.database.setup_db import get_db_session
from ada_backend.repositories.component_repository import get_instance_parameters_with_definition
from ada_backend.schemas.parameter_schema import PipelineParameterSchema
from ada_backend.schemas.pipeline.base import ComponentInstanceSchema
from ada_backend.services.pipeline.update_pipeline_service import create_or_update_component_instance
from tests.ada_backend.test_utils import create_project_and_graph_runner

AI_AGENT_COMPONENT_ID = COMPONENT_UUIDS["base_ai_agent"]
AI_AGENT_COMPONENT_VERSION_ID = COMPONENT_VERSION_UUIDS["base_ai_agent"]


def test_clone_ai_agent_with_missing_skip_oauth_param_uses_default():
    """
    Simulates the clone path: an AI Agent instance existed before
    skip_tools_with_missing_oauth was added, so when get_component_instance fills in
    missing parameters from the definition it sets value=None.

    create_or_update_component_instance must NOT raise and must store the default "True".
    """
    with get_db_session() as session:
        project_id, _ = create_project_and_graph_runner(session, project_name_prefix="dra_1149_regression")

        instance_data = ComponentInstanceSchema(
            component_id=AI_AGENT_COMPONENT_ID,
            component_version_id=AI_AGENT_COMPONENT_VERSION_ID,
            name="AI Agent",
            parameters=[
                PipelineParameterSchema(name="completion_model", value="openai:gpt-4o"),
                PipelineParameterSchema(name="skip_tools_with_missing_oauth", value=None),
            ],
        )

        instance_id = create_or_update_component_instance(session, instance_data, project_id)
        session.flush()

        stored_params = get_instance_parameters_with_definition(session, instance_id)
        skip_param = next(
            (p for p in stored_params if p.name == "skip_tools_with_missing_oauth"),
            None,
        )

        assert skip_param is not None, "skip_tools_with_missing_oauth should have been stored"
        assert skip_param.value is True, f"Expected default True to be stored, got {skip_param.value!r}"


def test_clone_ai_agent_with_explicit_skip_oauth_false_stores_false():
    """
    When an explicit value is provided (e.g. user had saved the param as False),
    the explicit value must be stored as-is, not overwritten by the default.
    """
    with get_db_session() as session:
        project_id, _ = create_project_and_graph_runner(session, project_name_prefix="dra_1149_explicit")

        instance_data = ComponentInstanceSchema(
            component_id=AI_AGENT_COMPONENT_ID,
            component_version_id=AI_AGENT_COMPONENT_VERSION_ID,
            name="AI Agent",
            parameters=[
                PipelineParameterSchema(name="completion_model", value="openai:gpt-4o"),
                PipelineParameterSchema(name="skip_tools_with_missing_oauth", value="False"),
            ],
        )

        instance_id = create_or_update_component_instance(session, instance_data, project_id)
        session.flush()

        stored_params = get_instance_parameters_with_definition(session, instance_id)
        skip_param = next(
            (p for p in stored_params if p.name == "skip_tools_with_missing_oauth"),
            None,
        )

        assert skip_param is not None
        assert skip_param.value is False
