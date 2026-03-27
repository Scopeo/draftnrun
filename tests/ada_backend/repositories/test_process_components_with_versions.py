"""Integration tests for process_components_with_versions()."""

import uuid
from uuid import UUID

import pytest
from sqlalchemy.orm import Session  # used in fixture type hints

from ada_backend.database import models as db
from ada_backend.database.setup_db import SessionLocal
from ada_backend.repositories.component_repository import (
    ComponentWithVersionDTO,
    process_components_with_versions,
)

# ---------------------------------------------------------------------------
# Stable UUIDs — chosen to be obviously synthetic and unlikely to collide
# with any real production row.
# ---------------------------------------------------------------------------
IDS: dict[str, UUID] = {
    "component":     UUID("cccc0001-0000-4000-8000-000000000001"),
    "version":       UUID("cccc0001-0000-4000-8000-000000000002"),
    "integration":   UUID("cccc0001-0000-4000-8000-000000000003"),
    "param_group":   UUID("cccc0001-0000-4000-8000-000000000005"),
    "cpg":           UUID("cccc0001-0000-4000-8000-000000000006"),
    "param_regular": UUID("cccc0001-0000-4000-8000-000000000007"),
    "param_global":  UUID("cccc0001-0000-4000-8000-000000000008"),
    # Second component for cross-contamination test
    "component2":    UUID("cccc0002-0000-4000-8000-000000000001"),
    "version2":      UUID("cccc0002-0000-4000-8000-000000000002"),
    "param2":        UUID("cccc0002-0000-4000-8000-000000000003"),
}


# ---------------------------------------------------------------------------
# Session fixture
# ---------------------------------------------------------------------------
@pytest.fixture
def session():
    # Uses flush() (not commit()) throughout, so rollback() wipes everything at the end.
    sess = SessionLocal()
    yield sess
    sess.rollback()
    sess.close()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def full_component(session: Session):
    integration = db.Integration(
        id=IDS["integration"],
        name="Test Gmail",
        service="gmail",
    )
    session.add(integration)

    component = db.Component(
        id=IDS["component"],
        name="__N1TestComponent__",
        description="Used by integration tests for N+1 fix",
        is_agent=False,
        function_callable=False,
        can_use_function_calling=False,
    )
    session.add(component)
    session.flush()

    version = db.ComponentVersion(
        id=IDS["version"],
        component_id=IDS["component"],
        version_tag="1.0.0",
        description="Test version",
        release_stage=db.ReleaseStage.INTERNAL,
        integration_id=IDS["integration"],
    )
    session.add(version)
    session.flush()

    param_group = db.ParameterGroup(
        id=IDS["param_group"],
        name="Advanced",
    )
    session.add(param_group)

    cpg = db.ComponentParameterGroup(
        id=IDS["cpg"],
        component_version_id=IDS["version"],
        parameter_group_id=IDS["param_group"],
        group_order_within_component=0,
    )
    session.add(cpg)

    param_regular = db.ComponentParameterDefinition(
        id=IDS["param_regular"],
        component_version_id=IDS["version"],
        name="recipient",
        type=db.ParameterType.STRING,
        nullable=False,
        ui_component=db.UIComponent.TEXTFIELD,
    )
    session.add(param_regular)

    param_global_def = db.ComponentParameterDefinition(
        id=IDS["param_global"],
        component_version_id=IDS["version"],
        name="api_key",
        type=db.ParameterType.STRING,
        nullable=False,
        ui_component=db.UIComponent.TEXTFIELD,
    )
    session.add(param_global_def)
    session.flush()

    global_param = db.ComponentGlobalParameter(
        component_version_id=IDS["version"],
        parameter_definition_id=IDS["param_global"],
        value="secret",
    )
    session.add(global_param)
    session.flush()


@pytest.fixture
def second_component(session: Session, full_component):
    component2 = db.Component(
        id=IDS["component2"],
        name="__N1TestComponent2__",
        description="Second component for cross-contamination test",
        is_agent=False,
        function_callable=False,
        can_use_function_calling=False,
    )
    session.add(component2)
    session.flush()

    version2 = db.ComponentVersion(
        id=IDS["version2"],
        component_id=IDS["component2"],
        version_tag="1.0.0",
        description="Second version",
        release_stage=db.ReleaseStage.INTERNAL,
    )
    session.add(version2)
    session.flush()

    param2 = db.ComponentParameterDefinition(
        id=IDS["param2"],
        component_version_id=IDS["version2"],
        name="only_param",
        type=db.ParameterType.STRING,
        nullable=True,
        ui_component=db.UIComponent.TEXTFIELD,
    )
    session.add(param2)
    session.flush()


# ---------------------------------------------------------------------------
# DTO helpers
# ---------------------------------------------------------------------------
def _make_dto(integration_id: UUID | None = IDS["integration"]) -> ComponentWithVersionDTO:
    return ComponentWithVersionDTO(
        component_id=IDS["component"],
        name="__N1TestComponent__",
        description="Used by integration tests for N+1 fix",
        component_version_id=IDS["version"],
        version_tag="1.0.0",
        release_stage=db.ReleaseStage.INTERNAL,
        is_agent=False,
        function_callable=False,
        can_use_function_calling=False,
        is_protected=False,
        integration_id=integration_id,
        category_ids=[],
    )


def _make_dto2() -> ComponentWithVersionDTO:
    return ComponentWithVersionDTO(
        component_id=IDS["component2"],
        name="__N1TestComponent2__",
        description="Second component for cross-contamination test",
        component_version_id=IDS["version2"],
        version_tag="1.0.0",
        release_stage=db.ReleaseStage.INTERNAL,
        is_agent=False,
        function_callable=False,
        can_use_function_calling=False,
        is_protected=False,
        integration_id=None,
        category_ids=[],
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
class TestProcessComponentsWithVersions:

    def test_empty_input_returns_empty(self, session: Session):
        result = process_components_with_versions(session, [])
        assert result == []

    def test_returns_one_result_per_input(self, session: Session, full_component):
        result = process_components_with_versions(session, [_make_dto()])
        assert len(result) == 1

    def test_basic_identity_fields(self, session: Session, full_component):
        comp = process_components_with_versions(session, [_make_dto()])[0]
        assert comp.id == IDS["component"]
        assert comp.name == "__N1TestComponent__"
        assert comp.component_version_id == IDS["version"]
        assert comp.version_tag == "1.0.0"

    def test_integration_is_populated(self, session: Session, full_component):
        comp = process_components_with_versions(session, [_make_dto()])[0]
        assert comp.integration is not None
        assert comp.integration.id == IDS["integration"]
        assert comp.integration.name == "Test Gmail"
        assert comp.integration.service == "gmail"

    def test_no_integration_returns_none(self, session: Session, full_component):
        comp = process_components_with_versions(session, [_make_dto(integration_id=None)])[0]
        assert comp.integration is None

    def test_tool_description_is_none(self, session: Session, full_component):
        comp = process_components_with_versions(session, [_make_dto()])[0]
        assert comp.tool_description is None

    def test_regular_param_is_present(self, session: Session, full_component):
        # 'recipient' is a regular param → must appear in parameters
        comp = process_components_with_versions(session, [_make_dto()])[0]
        assert "recipient" in [p.name for p in comp.parameters]

    def test_global_param_is_hidden(self, session: Session, full_component):
        # 'api_key' is marked global → must NOT appear (hidden from instance-level editing)
        comp = process_components_with_versions(session, [_make_dto()])[0]
        assert "api_key" not in [p.name for p in comp.parameters]

    def test_only_one_visible_param(self, session: Session, full_component):
        # fixture has 2 params: 1 regular + 1 global (hidden) → only 1 visible
        comp = process_components_with_versions(session, [_make_dto()])[0]
        assert len(comp.parameters) == 1

    def test_param_fields_are_correct(self, session: Session, full_component):
        comp = process_components_with_versions(session, [_make_dto()])[0]
        param = comp.parameters[0]
        assert param.id == IDS["param_regular"]
        assert param.name == "recipient"
        assert param.type == db.ParameterType.STRING
        assert param.nullable is False

    def test_parameter_group_is_populated(self, session: Session, full_component):
        comp = process_components_with_versions(session, [_make_dto()])[0]
        assert len(comp.parameter_groups) == 1
        assert comp.parameter_groups[0].name == "Advanced"
        assert comp.parameter_groups[0].group_order_within_component_version == 0

    def test_two_components_get_separate_data(self, session: Session, second_component):
        # comp1: has 'recipient', integration, tool description, parameter group
        # comp2: has 'only_param', no integration, no tool description, no group
        result = process_components_with_versions(session, [_make_dto(), _make_dto2()])
        assert len(result) == 2

        by_id = {r.id: r for r in result}
        comp1 = by_id[IDS["component"]]
        comp2 = by_id[IDS["component2"]]

        assert [p.name for p in comp1.parameters] == ["recipient"]
        assert comp1.integration is not None
        assert comp1.tool_description is None
        assert len(comp1.parameter_groups) == 1

        assert [p.name for p in comp2.parameters] == ["only_param"]
        assert comp2.integration is None
        assert comp2.tool_description is None
        assert len(comp2.parameter_groups) == 0

    def test_ghost_component_version_id_returns_empty_data(self, session: Session):
        # a DTO whose IDs don't exist in the DB must not crash and must return empty collections
        ghost_dto = ComponentWithVersionDTO(
            component_id=uuid.uuid4(),
            name="Ghost",
            description=None,
            component_version_id=uuid.uuid4(),
            version_tag="0.0.1",
            release_stage=db.ReleaseStage.INTERNAL,
            is_agent=False,
            function_callable=False,
            can_use_function_calling=False,
            is_protected=False,
            integration_id=None,
            category_ids=[],
        )
        result = process_components_with_versions(session, [ghost_dto])
        assert len(result) == 1
        assert result[0].parameters == []
        assert result[0].integration is None
        assert result[0].tool_description is None
        assert result[0].parameter_groups == []
