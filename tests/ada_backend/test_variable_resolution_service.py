"""Tests for variable_resolution_service.resolve_variables."""

import uuid

from ada_backend.database import models as db
from ada_backend.database.setup_db import get_db_session
from ada_backend.services.variable_resolution_service import resolve_variables


def _def(org_id, name, default_value=None):
    return db.OrgVariableDefinition(
        id=uuid.uuid4(),
        organization_id=org_id,
        name=name,
        type="string",
        default_value=default_value,
    )


def _set(org_id, set_id, values):
    return db.OrgVariableSet(
        id=uuid.uuid4(),
        organization_id=org_id,
        set_id=set_id,
        values=values,
    )


def test_resolve_defaults_only():
    org_id = uuid.uuid4()
    with get_db_session() as session:
        session.add(_def(org_id, "var_a", default_value="default_a"))
        session.add(_def(org_id, "var_b", default_value="default_b"))
        session.flush()

        result = resolve_variables(session, org_id, [])

    assert result == {"var_a": "default_a", "var_b": "default_b"}


def test_resolve_single_set_overrides():
    org_id = uuid.uuid4()
    with get_db_session() as session:
        session.add(_def(org_id, "var_a", default_value="default_a"))
        session.add(_def(org_id, "var_b", default_value="default_b"))
        session.add(_set(org_id, "set1", {"var_a": "overridden_a"}))
        session.flush()

        result = resolve_variables(session, org_id, ["set1"])

    assert result == {"var_a": "overridden_a", "var_b": "default_b"}


def test_resolve_multiple_sets_layer_order():
    org_id = uuid.uuid4()
    with get_db_session() as session:
        session.add(_def(org_id, "var_a", default_value="default_a"))
        session.add(_def(org_id, "var_b", default_value="default_b"))
        session.add(_set(org_id, "set1", {"var_a": "from_set1"}))
        session.add(_set(org_id, "set2", {"var_a": "from_set2"}))
        session.flush()

        result = resolve_variables(session, org_id, ["set1", "set2"])

    assert result["var_a"] == "from_set2"
    assert result["var_b"] == "default_b"


def test_resolve_unknown_set_ignored():
    org_id = uuid.uuid4()
    with get_db_session() as session:
        session.add(_def(org_id, "var_a", default_value="default_a"))
        session.add(_def(org_id, "var_b", default_value="default_b"))
        session.flush()

        result = resolve_variables(session, org_id, ["nonexistent"])

    assert result == {"var_a": "default_a", "var_b": "default_b"}


def test_resolve_extra_keys_in_set_ignored():
    org_id = uuid.uuid4()
    with get_db_session() as session:
        session.add(_def(org_id, "var_a", default_value="default_a"))
        session.add(
            _set(org_id, "set1", {"var_a": "x", "extra_key": "y"})
        )
        session.flush()

        result = resolve_variables(session, org_id, ["set1"])

    assert result == {"var_a": "x"}
    assert "extra_key" not in result


def test_resolve_empty_definitions():
    org_id = uuid.uuid4()
    with get_db_session() as session:
        session.add(_set(org_id, "set1", {"var_a": "x"}))
        session.flush()

        result = resolve_variables(session, org_id, ["set1"])

    assert result == {}
