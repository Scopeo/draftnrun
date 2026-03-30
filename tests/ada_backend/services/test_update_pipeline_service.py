"""
Regression tests for create_or_update_component_instance in update_pipeline_service.

When cloning a component instance that has a non-nullable parameter with a default
value but no stored row in basic_parameters, the copy path passes value=None.
The fix falls back to param_def.default instead of raising ValueError.

Integration tests that run against the real seeded database.
"""

from unittest.mock import patch

import pytest

from ada_backend.database import models as db
from ada_backend.database.seed.utils import COMPONENT_UUIDS, COMPONENT_VERSION_UUIDS
from ada_backend.database.setup_db import get_db_session
from ada_backend.repositories.component_repository import get_instance_parameters_with_definition
from ada_backend.schemas.parameter_schema import PipelineParameterSchema
from ada_backend.schemas.pipeline.base import ComponentInstanceSchema
from ada_backend.services.pipeline.update_pipeline_service import (
    _normalize_expression_json,
    create_or_update_component_instance,
)
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


def test_non_nullable_param_without_default_raises():
    """
    When a parameter is non-nullable, has no default, and value=None is passed,
    create_or_update_component_instance must still raise ValueError.

    This guards against over-defaulting: the fallback to param_def.default must
    only apply when a default actually exists.

    We inject a fake parameter definition so the test is not coupled to a specific
    component having a truly-required param in the seed.
    """
    fake_param_def = db.ComponentParameterDefinition(
        id=COMPONENT_UUIDS["base_ai_agent"],
        component_version_id=COMPONENT_VERSION_UUIDS["base_ai_agent"],
        name="truly_required_param",
        type=db.ParameterType.STRING,
        nullable=False,
        default=None,
    )

    with get_db_session() as session:
        project_id, _ = create_project_and_graph_runner(session, project_name_prefix="dra_1149_raises")

        instance_data = ComponentInstanceSchema(
            component_id=COMPONENT_UUIDS["base_ai_agent"],
            component_version_id=COMPONENT_VERSION_UUIDS["base_ai_agent"],
            name="AI Agent",
            parameters=[
                PipelineParameterSchema(name="truly_required_param", value=None),
            ],
        )

        with patch(
            "ada_backend.services.pipeline.update_pipeline_service.get_component_parameter_definition_by_component_version",
            return_value=[fake_param_def],
        ):
            with pytest.raises(ValueError, match="cannot be None"):
                create_or_update_component_instance(session, instance_data, project_id)


class TestNormalizeExpressionJson:
    """Regression tests for DRA-1151: raw scalars in ToolPortConfiguration.expression_json."""

    def test_none_returns_none(self):
        assert _normalize_expression_json(None) is None

    def test_raw_string_becomes_literal_ast(self):
        result = _normalize_expression_json("pablo@draftnrun.com")
        assert result == {"type": "literal", "value": "pablo@draftnrun.com"}

    def test_raw_numeric_string_becomes_literal_ast(self):
        result = _normalize_expression_json("42")
        assert result == {"type": "literal", "value": "42"}

    def test_proper_ast_dict_is_preserved(self):
        ast_dict = {"type": "literal", "value": "hello"}
        result = _normalize_expression_json(ast_dict)
        assert result == {"type": "literal", "value": "hello"}

    def test_var_ast_dict_is_preserved(self):
        ast_dict = {"type": "var", "name": "my_secret"}
        result = _normalize_expression_json(ast_dict)
        assert result == {"type": "var", "name": "my_secret"}

    def test_raw_dict_becomes_literal_json(self):
        raw = {"foo": "bar"}
        result = _normalize_expression_json(raw)
        assert result == {"type": "literal", "value": '{"foo": "bar"}'}

    def test_raw_list_becomes_literal_json(self):
        raw = [1, 2, 3]
        result = _normalize_expression_json(raw)
        assert result == {"type": "literal", "value": "[1, 2, 3]"}

    def test_raw_int_becomes_literal_ast(self):
        result = _normalize_expression_json(42)
        assert result == {"type": "literal", "value": "42"}

    def test_raw_bool_becomes_literal_ast(self):
        result = _normalize_expression_json(True)
        assert result == {"type": "literal", "value": "True"}

    def test_string_with_ref_becomes_ref_ast(self):
        result = _normalize_expression_json("@{{comp.port}}")
        assert result == {"type": "ref", "instance": "comp", "port": "port"}
