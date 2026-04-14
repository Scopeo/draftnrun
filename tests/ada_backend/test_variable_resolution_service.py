"""Tests for variable_resolution_service.resolve_variables."""

import uuid

from ada_backend.database import models as db
from ada_backend.database.setup_db import get_db_session
from ada_backend.services.variable_resolution_service import resolve_variables
from ada_backend.services.variables_service import upsert_set_service
from engine.secret import SecretValue


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
        session.add(_set(org_id, "set1", {"var_a": "x", "extra_key": "y"}))
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


def test_resolve_set_overrides_oauth_definition_default():
    """Set value overrides the default_value on an oauth-type definition."""
    org_id = uuid.uuid4()
    default_conn_id = str(uuid.uuid4())
    user_conn_id = str(uuid.uuid4())
    with get_db_session() as session:
        session.add(
            db.OrgVariableDefinition(
                id=uuid.uuid4(),
                organization_id=org_id,
                name="google-mail-oauth",
                type="oauth",
                default_value=default_conn_id,
            )
        )
        session.add(_set(org_id, "user_set", {"google-mail-oauth": user_conn_id}))
        session.flush()

        result = resolve_variables(session, org_id, ["user_set"])

    assert result["google-mail-oauth"] == user_conn_id


def test_resolve_secret_values_from_encrypted_storage():
    org_id = uuid.uuid4()
    def_id = uuid.uuid4()
    set_uuid = uuid.uuid4()

    with get_db_session() as session:
        session.add(
            db.OrgVariableDefinition(
                id=def_id,
                organization_id=org_id,
                name="api_key",
                type=db.VariableType.SECRET,
            )
        )
        session.add(_def(org_id, "var_a", default_value="default_a"))
        session.add(
            db.OrgVariableSet(
                id=set_uuid,
                organization_id=org_id,
                set_id="set1",
                values={"var_a": "override_a"},
            )
        )
        session.flush()

        org_secret = db.OrganizationSecret(
            organization_id=org_id,
            key="api_key",
            secret_type=db.OrgSecretType.VARIABLE,
            variable_definition_id=def_id,
            variable_set_id=set_uuid,
        )
        org_secret.set_secret("super-secret")
        session.add(org_secret)
        session.flush()

        result = resolve_variables(session, org_id, ["set1"])

    assert result["var_a"] == "override_a"
    assert result["api_key"] == SecretValue("super-secret")


def test_resolve_secret_end_to_end_via_upsert_service():
    """upsert_set_service cifra → resolve_variables descifra. Ciclo completo con DB."""
    org_id = uuid.uuid4()
    with get_db_session() as session:
        session.add(
            db.OrgVariableDefinition(
                id=uuid.uuid4(),
                organization_id=org_id,
                name="api_key",
                type=db.VariableType.SECRET,
            )
        )
        session.add(_def(org_id, "api_url"))
        session.flush()

        upsert_set_service(
            session,
            org_id,
            "set1",
            {
                "api_url": "https://example.com",
                "api_key": "my-secret-value",
            },
        )

        result = resolve_variables(session, org_id, ["set1"])

    assert result["api_url"] == "https://example.com"
    assert result["api_key"] == SecretValue("my-secret-value")


def test_resolve_secret_not_set_excluded():
    """Un secret sin valor en encrypted_values no aparece en el resultado."""
    org_id = uuid.uuid4()
    with get_db_session() as session:
        session.add(
            db.OrgVariableDefinition(
                id=uuid.uuid4(),
                organization_id=org_id,
                name="api_key",
                type=db.VariableType.SECRET,
            )
        )
        session.add(_def(org_id, "var_a", default_value="default_a"))
        session.add(
            db.OrgVariableSet(
                id=uuid.uuid4(),
                organization_id=org_id,
                set_id="set1",
                values={"var_a": "override_a"},
            )
        )
        session.flush()

        result = resolve_variables(session, org_id, ["set1"])

    assert result["var_a"] == "override_a"
    assert "api_key" not in result
