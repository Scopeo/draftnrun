import pytest

pytestmark = pytest.mark.alembic

from pytest_alembic.tests import test_single_head_revision
from pytest_alembic.tests import test_upgrade
from pytest_alembic.tests import test_up_down_consistency

from pytest_alembic.config import Config
from pytest_mock_resources import create_postgres_fixture


# Dedicated ephemeral Postgres for trace alembic tests
alembic_engine = create_postgres_fixture()


@pytest.fixture
def alembic_config():
    return Config(config_options={"file": "engine/trace/alembic.ini"})
