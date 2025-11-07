import pytest

pytestmark = pytest.mark.alembic

from pytest_alembic.tests import test_single_head_revision
from pytest_alembic.tests import test_upgrade
from pytest_alembic.tests import test_up_down_consistency

# TODO: Uncomment when non-empty revision issue is fixed
# from pytest_alembic.tests import test_model_definitions_match_ddl
