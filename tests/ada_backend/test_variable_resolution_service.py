"""Integration tests for variable_resolution_service.resolve_variables."""

import os
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from ada_backend.database import setup_db
from ada_backend.repositories import variable_definitions_repository, variable_sets_repository
from ada_backend.services.variable_resolution_service import resolve_variables
from settings import settings


@pytest.fixture(scope="function")
def db_session(alembic_engine, alembic_runner):
    if settings.ADA_DB_URL:
        try:
            engine = create_engine(settings.ADA_DB_URL, echo=False)
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        except Exception as e:
            if not os.getenv("CI"):
                pytest.skip(
                    f"Could not connect to real database: {e}. "
                    "Ensure ADA_DB_URL is set and database is accessible."
                )
            raise
    else:
        engine = alembic_engine
        alembic_runner.migrate_up_to("heads", return_current=False)

    original_engine = setup_db.engine
    setup_db.SessionLocal.configure(bind=engine)
    SessionFactory = sessionmaker(bind=engine)
    connection = engine.connect()
    transaction = connection.begin()
    session = SessionFactory(bind=connection)
    try:
        yield session
    finally:
        transaction.rollback()
        session.close()
        connection.close()
        setup_db.SessionLocal.configure(bind=original_engine)


@pytest.fixture
def org_id():
    return uuid.uuid4()


def test_resolve_defaults_only(db_session, org_id):
    variable_definitions_repository.upsert_org_definition(
        db_session, org_id, "var_a", type="string", default_value="default_a"
    )
    variable_definitions_repository.upsert_org_definition(
        db_session, org_id, "var_b", type="string", default_value="default_b"
    )

    result = resolve_variables(db_session, org_id, [])

    assert result == {"var_a": "default_a", "var_b": "default_b"}


def test_resolve_single_set_overrides(db_session, org_id):
    variable_definitions_repository.upsert_org_definition(
        db_session, org_id, "var_a", type="string", default_value="default_a"
    )
    variable_definitions_repository.upsert_org_definition(
        db_session, org_id, "var_b", type="string", default_value="default_b"
    )
    variable_sets_repository.upsert_org_variable_set(
        db_session, org_id, "set1", values={"var_a": "overridden_a"}
    )

    result = resolve_variables(db_session, org_id, ["set1"])

    assert result == {"var_a": "overridden_a", "var_b": "default_b"}


def test_resolve_multiple_sets_layer_order(db_session, org_id):
    variable_definitions_repository.upsert_org_definition(
        db_session, org_id, "var_a", type="string", default_value="default_a"
    )
    variable_definitions_repository.upsert_org_definition(
        db_session, org_id, "var_b", type="string", default_value="default_b"
    )
    variable_sets_repository.upsert_org_variable_set(
        db_session, org_id, "set1", values={"var_a": "from_set1"}
    )
    variable_sets_repository.upsert_org_variable_set(
        db_session, org_id, "set2", values={"var_a": "from_set2"}
    )

    result = resolve_variables(db_session, org_id, ["set1", "set2"])

    assert result["var_a"] == "from_set2"
    assert result["var_b"] == "default_b"


def test_resolve_unknown_set_ignored(db_session, org_id):
    variable_definitions_repository.upsert_org_definition(
        db_session, org_id, "var_a", type="string", default_value="default_a"
    )
    variable_definitions_repository.upsert_org_definition(
        db_session, org_id, "var_b", type="string", default_value="default_b"
    )

    result = resolve_variables(db_session, org_id, ["nonexistent"])

    assert result == {"var_a": "default_a", "var_b": "default_b"}


def test_resolve_extra_keys_in_set_ignored(db_session, org_id):
    variable_definitions_repository.upsert_org_definition(
        db_session, org_id, "var_a", type="string", default_value="default_a"
    )
    variable_sets_repository.upsert_org_variable_set(
        db_session, org_id, "set1", values={"var_a": "x", "extra_key": "y"}
    )

    result = resolve_variables(db_session, org_id, ["set1"])

    assert result == {"var_a": "x"}
    assert "extra_key" not in result


def test_resolve_empty_definitions(db_session, org_id):
    variable_sets_repository.upsert_org_variable_set(
        db_session, org_id, "set1", values={"var_a": "x"}
    )

    result = resolve_variables(db_session, org_id, ["set1"])

    assert result == {}
