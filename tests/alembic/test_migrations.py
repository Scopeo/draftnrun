from collections import defaultdict
from uuid import UUID

import pytest

pytestmark = pytest.mark.alembic

from pytest_alembic.tests import (
    test_model_definitions_match_ddl,
    test_single_head_revision,
    test_up_down_consistency,
    test_upgrade,
)
from sqlalchemy.orm import sessionmaker

from ada_backend.database import models as db
from ada_backend.database.seed_db import seed_db
from ada_backend.database.seed_project_db import seed_projects_db

# UUIDs that are known to collide across tables due to a pre-existing condition
# that cannot be changed without breaking existing databases.
_KNOWN_EXISTING_CROSS_TABLE_DUPLICATES: set[UUID] = {
    # categories.most_used == tool_descriptions.default_retriever_tool_description
    UUID("b1c2d3e4-f5a6-7b8c-9d0e-1f2a3b4c5d6e"),
    # component_parameter_definitions (api_call_tool "method" param)
    #   == parameter_groups (ai_agent history_management group)
    UUID("c3d4e5f6-a7b8-9012-cdef-123456789012"),
}

_SEED_TABLES: list[tuple[str, type]] = [
    ("components", db.Component),
    ("component_versions", db.ComponentVersion),
    ("tool_descriptions", db.ToolDescription),
    ("categories", db.Category),
    ("component_parameter_definitions", db.ComponentParameterDefinition),
    ("parameter_groups", db.ParameterGroup),
    ("integrations", db.Integration),
]


def _assert_seed_uuid_uniqueness(session) -> None:
    """Assert no UUID appears as a PK in more than one seed table.

    Accepted exceptions:
    - Component first-version pattern: a component's first version intentionally
      reuses the component's own UUID (component_id == version_id).
    - _KNOWN_EXISTING_CROSS_TABLE_DUPLICATES: pre-existing cross-table collisions
      that cannot be changed without breaking existing databases.
    """
    sources_by_uuid: dict[UUID, list[str]] = defaultdict(list)
    for table_name, model in _SEED_TABLES:
        for (uuid_val,) in session.query(model.id).all():
            sources_by_uuid[uuid_val].append(table_name)

    component_ids = {row[0] for row in session.query(db.Component.id).all()}
    version_ids = {row[0] for row in session.query(db.ComponentVersion.id).all()}
    allowed_component_version_overlap = component_ids & version_ids

    unexpected_duplicates = {
        uuid_val: tables
        for uuid_val, tables in sources_by_uuid.items()
        if len(tables) > 1
        and uuid_val not in allowed_component_version_overlap
        and uuid_val not in _KNOWN_EXISTING_CROSS_TABLE_DUPLICATES
    }

    if unexpected_duplicates:
        descriptions = [
            f"{uuid_val}: {', '.join(sorted(tables))}"
            for uuid_val, tables in sorted(unexpected_duplicates.items(), key=str)
        ]
        pytest.fail("Unexpected duplicate UUIDs across seed tables: " + "; ".join(descriptions))


def test_upgrade_and_seed(alembic_runner, alembic_engine):
    """Upgrade to head, then run full database seeding."""
    alembic_runner.migrate_up_to("heads", return_current=False)

    Session = sessionmaker(bind=alembic_engine)
    session = Session()
    try:
        seed_db(session)
        seed_projects_db(session)
        _assert_seed_uuid_uniqueness(session)
    finally:
        session.close()
