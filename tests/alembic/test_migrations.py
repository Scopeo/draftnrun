import pytest

pytestmark = pytest.mark.alembic

from pytest_alembic.tests import test_single_head_revision
from pytest_alembic.tests import test_upgrade
from pytest_alembic.tests import test_up_down_consistency
from pytest_alembic.tests import test_model_definitions_match_ddl

from sqlalchemy.orm import sessionmaker
from ada_backend.database.seed_db import seed_db
from ada_backend.database.seed_project_db import seed_projects_db


def test_upgrade_and_seed(alembic_runner, alembic_engine):
    """Upgrade to head, then run full database seeding."""
    alembic_runner.migrate_up_to("heads", return_current=False)

    Session = sessionmaker(bind=alembic_engine)
    session = Session()
    try:
        seed_db(session)
        seed_projects_db(session)
    finally:
        session.close()
