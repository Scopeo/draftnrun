"""Tests for variables_service – definition upsert & list with project scoping."""

import uuid

import pytest

from ada_backend.database import models as db
from ada_backend.database.setup_db import get_db_session
from ada_backend.schemas.variable_schemas import VariableDefinitionUpsertRequest
from ada_backend.services.variables_service import (
    list_definitions_service,
    upsert_definition_service,
)


def _project(org_id):
    pid = uuid.uuid4()
    return db.WorkflowProject(
        id=pid,
        name=f"proj-{pid.hex[:8]}",
        organization_id=org_id,
        type=db.ProjectType.WORKFLOW,
    )


def test_upsert_with_project_ids():
    """Upsert with project_ids=[A, B] → stored correctly."""
    org_id = uuid.uuid4()
    pa_id = uuid.uuid4()
    pb_id = uuid.uuid4()
    with get_db_session() as session:
        session.add(db.WorkflowProject(id=pa_id, name="pa", organization_id=org_id, type=db.ProjectType.WORKFLOW))
        session.add(db.WorkflowProject(id=pb_id, name="pb", organization_id=org_id, type=db.ProjectType.WORKFLOW))
        session.flush()

        body = VariableDefinitionUpsertRequest(type="string", project_ids=[pa_id, pb_id])
        result = upsert_definition_service(session, org_id, "test_var", body)

    assert result.name == "test_var"
    assert set(result.project_ids) == {pa_id, pb_id}


def test_upsert_with_empty_project_ids_clears():
    """Upsert with project_ids=[] → clears all (global)."""
    org_id = uuid.uuid4()
    pa_id = uuid.uuid4()
    with get_db_session() as session:
        session.add(db.WorkflowProject(id=pa_id, name="pa", organization_id=org_id, type=db.ProjectType.WORKFLOW))
        session.flush()

        body = VariableDefinitionUpsertRequest(type="string", project_ids=[pa_id])
        upsert_definition_service(session, org_id, "test_var", body)

        body2 = VariableDefinitionUpsertRequest(type="string", project_ids=[])
        result = upsert_definition_service(session, org_id, "test_var", body2)

    assert result.project_ids == []


def test_upsert_with_project_ids_omitted_preserves():
    """Upsert with project_ids omitted → existing associations preserved."""
    org_id = uuid.uuid4()
    pa_id = uuid.uuid4()
    with get_db_session() as session:
        session.add(db.WorkflowProject(id=pa_id, name="pa", organization_id=org_id, type=db.ProjectType.WORKFLOW))
        session.flush()

        body = VariableDefinitionUpsertRequest(type="string", project_ids=[pa_id])
        upsert_definition_service(session, org_id, "test_var", body)

        body2 = VariableDefinitionUpsertRequest(type="string", description="updated")
        result = upsert_definition_service(session, org_id, "test_var", body2)

    assert result.project_ids == [pa_id]
    assert result.description == "updated"


def test_upsert_with_duplicate_project_ids_deduped():
    """Upsert with project_ids=[A, A] → deduped, no error."""
    org_id = uuid.uuid4()
    pa_id = uuid.uuid4()
    with get_db_session() as session:
        session.add(db.WorkflowProject(id=pa_id, name="pa", organization_id=org_id, type=db.ProjectType.WORKFLOW))
        session.flush()

        body = VariableDefinitionUpsertRequest(type="string", project_ids=[pa_id, pa_id])
        result = upsert_definition_service(session, org_id, "test_var", body)

    assert result.project_ids == [pa_id]


def test_upsert_with_cross_org_project_id_raises():
    """Upsert with cross-org project_id → ValueError."""
    org_id = uuid.uuid4()
    other_org_id = uuid.uuid4()
    other_pid = uuid.uuid4()
    with get_db_session() as session:
        session.add(
            db.WorkflowProject(
                id=other_pid,
                name="other",
                organization_id=other_org_id,
                type=db.ProjectType.WORKFLOW,
            )
        )
        session.flush()

        body = VariableDefinitionUpsertRequest(type="string", project_ids=[other_pid])
        with pytest.raises(ValueError, match="does not belong to organization"):
            upsert_definition_service(session, org_id, "test_var", body)


def test_list_with_project_id_filter():
    """List with project_id filter → returns project-scoped + global."""
    org_id = uuid.uuid4()
    pa_id = uuid.uuid4()
    with get_db_session() as session:
        session.add(db.WorkflowProject(id=pa_id, name="pa", organization_id=org_id, type=db.ProjectType.WORKFLOW))
        session.flush()

        body_scoped = VariableDefinitionUpsertRequest(type="string", project_ids=[pa_id])
        upsert_definition_service(session, org_id, "scoped_var", body_scoped)

        body_global = VariableDefinitionUpsertRequest(type="string", project_ids=[])
        upsert_definition_service(session, org_id, "global_var", body_global)

        result = list_definitions_service(session, org_id, project_id=pa_id)

    names = {r.name for r in result}
    assert "scoped_var" in names
    assert "global_var" in names


def test_list_without_filter_returns_all():
    """List without filter → returns all."""
    org_id = uuid.uuid4()
    pa_id = uuid.uuid4()
    pb_id = uuid.uuid4()
    with get_db_session() as session:
        session.add(db.WorkflowProject(id=pa_id, name="pa", organization_id=org_id, type=db.ProjectType.WORKFLOW))
        session.add(db.WorkflowProject(id=pb_id, name="pb", organization_id=org_id, type=db.ProjectType.WORKFLOW))
        session.flush()

        body_a = VariableDefinitionUpsertRequest(type="string", project_ids=[pa_id])
        upsert_definition_service(session, org_id, "var_a", body_a)

        body_b = VariableDefinitionUpsertRequest(type="number", project_ids=[pb_id])
        upsert_definition_service(session, org_id, "var_b", body_b)

        body_global = VariableDefinitionUpsertRequest(type="string", project_ids=[])
        upsert_definition_service(session, org_id, "var_global", body_global)

        result = list_definitions_service(session, org_id)

    assert len(result) == 3
    names = {r.name for r in result}
    assert names == {"var_a", "var_b", "var_global"}
