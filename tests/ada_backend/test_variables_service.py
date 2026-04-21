"""Tests for variables_service – definition upsert & list with project scoping."""

import uuid
from datetime import datetime

import pytest

from ada_backend.database import models as db
from ada_backend.database.setup_db import get_db_session
from ada_backend.schemas.variable_schemas import VariableDefinitionUpsertRequest
from ada_backend.services.errors import ProjectNotInOrganization
from ada_backend.services.variables_service import (
    get_set_service,
    list_definitions_service,
    list_sets_service,
    upsert_definition_service,
    upsert_set_service,
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
        with pytest.raises(ProjectNotInOrganization, match="does not belong to organization"):
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


# --- Secret encryption tests ---


def _definition(
    org_id: uuid.UUID, name: str, type: db.VariableType = db.VariableType.STRING
) -> db.OrgVariableDefinition:
    return db.OrgVariableDefinition(
        id=uuid.uuid4(),
        organization_id=org_id,
        name=name,
        type=type,
    )


def _set(
    org_id: uuid.UUID,
    set_id: str,
    values: dict,
    variable_type: db.VariableType = db.VariableType.VARIABLE,
) -> db.OrgVariableSet:
    now = datetime.utcnow()
    return db.OrgVariableSet(
        id=uuid.uuid4(),
        organization_id=org_id,
        set_id=set_id,
        variable_type=variable_type,
        values=values,
        created_at=now,
        updated_at=now,
    )


def test_upsert_set_service_stores_secret_and_masks_response(mocker):
    org_id = uuid.uuid4()
    api_url_def = _definition(org_id, "api_url")
    api_key_def = _definition(org_id, "api_key", type=db.VariableType.SECRET)
    definitions = [api_url_def, api_key_def]

    fake_variable_set = _set(org_id, "neverdrop", {"api_url": "https://example.com"})
    captured_secret = {}

    def fake_upsert_secret(_session, _org_id, def_id, set_id, key, secret):
        captured_secret["def_id"] = def_id
        captured_secret["key"] = key
        captured_secret["secret"] = secret

    fake_org_secret = mocker.MagicMock()
    fake_org_secret.key = "api_key"

    mocker.patch("ada_backend.services.variables_service.get_org_variable_set", return_value=None)
    mocker.patch("ada_backend.services.variables_service.list_org_definitions", return_value=definitions)
    mocker.patch("ada_backend.services.variables_service.upsert_org_variable_set", return_value=fake_variable_set)
    mocker.patch("ada_backend.services.variables_service.upsert_variable_secret", side_effect=fake_upsert_secret)
    mocker.patch(
        "ada_backend.services.variables_service.list_variable_secrets_for_set",
        return_value=[fake_org_secret],
    )

    response = upsert_set_service(
        session=None,
        organization_id=org_id,
        set_id="neverdrop",
        values={"api_url": "https://example.com", "api_key": "top-secret"},
    )

    assert captured_secret["def_id"] == api_key_def.id
    assert captured_secret["key"] == "api_key"
    assert captured_secret["secret"] == "top-secret"
    assert response.values == {
        "api_url": "https://example.com",
        "api_key": {"has_value": True},
    }


def test_upsert_set_service_preserves_existing_secret_when_none(mocker):
    org_id = uuid.uuid4()
    definitions = [
        _definition(org_id, "api_url"),
        _definition(org_id, "api_key", type=db.VariableType.SECRET),
    ]
    fake_variable_set = _set(org_id, "neverdrop", {"api_url": "https://after.example.com"})
    mock_upsert_secret = mocker.patch("ada_backend.services.variables_service.upsert_variable_secret")

    fake_org_secret = mocker.MagicMock()
    fake_org_secret.key = "api_key"

    mocker.patch("ada_backend.services.variables_service.get_org_variable_set", return_value=None)
    mocker.patch("ada_backend.services.variables_service.list_org_definitions", return_value=definitions)
    mocker.patch("ada_backend.services.variables_service.upsert_org_variable_set", return_value=fake_variable_set)
    mocker.patch(
        "ada_backend.services.variables_service.list_variable_secrets_for_set",
        return_value=[fake_org_secret],
    )

    response = upsert_set_service(
        session=None,
        organization_id=org_id,
        set_id="neverdrop",
        values={"api_url": "https://after.example.com", "api_key": None},
    )

    mock_upsert_secret.assert_not_called()
    assert response.values == {
        "api_url": "https://after.example.com",
        "api_key": {"has_value": True},
    }


def test_get_and_list_set_services_mask_secret_values(mocker):
    org_id = uuid.uuid4()
    variable_set = _set(org_id, "neverdrop", {"api_url": "https://example.com"})

    fake_org_secret = mocker.MagicMock()
    fake_org_secret.key = "api_key"

    mocker.patch("ada_backend.services.variables_service.get_org_variable_set", return_value=variable_set)
    mocker.patch("ada_backend.services.variables_service.list_org_variable_sets", return_value=[variable_set])
    mocker.patch(
        "ada_backend.services.variables_service.list_variable_secrets_for_set",
        return_value=[fake_org_secret],
    )

    single = get_set_service(session=None, organization_id=org_id, set_id="neverdrop")
    listing = list_sets_service(session=None, organization_id=org_id)

    expected = {"api_url": "https://example.com", "api_key": {"has_value": True}}
    assert single.values == expected
    assert listing.variable_sets[0].values == expected
