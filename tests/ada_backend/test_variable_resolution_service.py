"""Tests for variable_resolution_service.resolve_variables."""

import uuid
from datetime import datetime

from ada_backend.database import models as db
from ada_backend.database.models import CIPHER
from ada_backend.services.variable_resolution_service import resolve_variables


def _definition(org_id, name, default_value=None, type=db.VariableType.STRING):
    return db.OrgVariableDefinition(
        id=uuid.uuid4(),
        organization_id=org_id,
        name=name,
        type=type,
        default_value=default_value,
    )


def _set(org_id, set_id, values, encrypted_values=None):
    now = datetime.utcnow()
    return db.OrgVariableSet(
        id=uuid.uuid4(),
        organization_id=org_id,
        set_id=set_id,
        values=values,
        encrypted_values=encrypted_values or {},
        created_at=now,
        updated_at=now,
    )


def test_resolve_defaults_only(mocker):
    org_id = uuid.uuid4()
    mocker.patch(
        "ada_backend.services.variable_resolution_service.list_org_definitions",
        return_value=[
            _definition(org_id, "var_a", default_value="default_a"),
            _definition(org_id, "var_b", default_value="default_b"),
        ],
    )
    mocker.patch("ada_backend.services.variable_resolution_service.get_org_variable_set", return_value=None)

    result = resolve_variables(session=None, organization_id=org_id, set_ids=[])

    assert result == {"var_a": "default_a", "var_b": "default_b"}


def test_resolve_single_set_overrides(mocker):
    org_id = uuid.uuid4()
    mocker.patch(
        "ada_backend.services.variable_resolution_service.list_org_definitions",
        return_value=[
            _definition(org_id, "var_a", default_value="default_a"),
            _definition(org_id, "var_b", default_value="default_b"),
        ],
    )
    mocker.patch(
        "ada_backend.services.variable_resolution_service.get_org_variable_set",
        side_effect=lambda _session, _org_id, set_id: _set(org_id, set_id, {"var_a": "overridden_a"}),
    )

    result = resolve_variables(session=None, organization_id=org_id, set_ids=["set1"])

    assert result == {"var_a": "overridden_a", "var_b": "default_b"}


def test_resolve_multiple_sets_layer_order(mocker):
    org_id = uuid.uuid4()
    mocker.patch(
        "ada_backend.services.variable_resolution_service.list_org_definitions",
        return_value=[
            _definition(org_id, "var_a", default_value="default_a"),
            _definition(org_id, "var_b", default_value="default_b"),
        ],
    )
    sets = {
        "set1": _set(org_id, "set1", {"var_a": "from_set1"}),
        "set2": _set(org_id, "set2", {"var_a": "from_set2"}),
    }
    mocker.patch(
        "ada_backend.services.variable_resolution_service.get_org_variable_set",
        side_effect=lambda _session, _org_id, set_id: sets.get(set_id),
    )

    result = resolve_variables(session=None, organization_id=org_id, set_ids=["set1", "set2"])

    assert result["var_a"] == "from_set2"
    assert result["var_b"] == "default_b"


def test_resolve_unknown_set_ignored(mocker):
    org_id = uuid.uuid4()
    mocker.patch(
        "ada_backend.services.variable_resolution_service.list_org_definitions",
        return_value=[
            _definition(org_id, "var_a", default_value="default_a"),
            _definition(org_id, "var_b", default_value="default_b"),
        ],
    )
    mocker.patch("ada_backend.services.variable_resolution_service.get_org_variable_set", return_value=None)

    result = resolve_variables(session=None, organization_id=org_id, set_ids=["nonexistent"])

    assert result == {"var_a": "default_a", "var_b": "default_b"}


def test_resolve_extra_keys_in_set_ignored(mocker):
    org_id = uuid.uuid4()
    mocker.patch(
        "ada_backend.services.variable_resolution_service.list_org_definitions",
        return_value=[_definition(org_id, "var_a", default_value="default_a")],
    )
    mocker.patch(
        "ada_backend.services.variable_resolution_service.get_org_variable_set",
        return_value=_set(org_id, "set1", {"var_a": "x", "extra_key": "y"}),
    )

    result = resolve_variables(session=None, organization_id=org_id, set_ids=["set1"])

    assert result == {"var_a": "x"}
    assert "extra_key" not in result


def test_resolve_empty_definitions(mocker):
    org_id = uuid.uuid4()
    mocker.patch("ada_backend.services.variable_resolution_service.list_org_definitions", return_value=[])
    mocker.patch(
        "ada_backend.services.variable_resolution_service.get_org_variable_set",
        return_value=_set(org_id, "set1", {"var_a": "x"}),
    )

    result = resolve_variables(session=None, organization_id=org_id, set_ids=["set1"])

    assert result == {}


def test_resolve_secret_values_from_encrypted_storage(mocker):
    org_id = uuid.uuid4()
    mocker.patch(
        "ada_backend.services.variable_resolution_service.list_org_definitions",
        return_value=[
            _definition(org_id, "api_key", type=db.VariableType.SECRET),
            _definition(org_id, "var_a", default_value="default_a"),
        ],
    )
    mocker.patch(
        "ada_backend.services.variable_resolution_service.get_org_variable_set",
        return_value=_set(
            org_id,
            "set1",
            {"var_a": "override_a", "api_key": "legacy-plaintext"},
            encrypted_values={"api_key": CIPHER.encrypt(b"super-secret").decode()},
        ),
    )

    result = resolve_variables(session=None, organization_id=org_id, set_ids=["set1"])

    assert result == {"var_a": "override_a", "api_key": "super-secret"}
