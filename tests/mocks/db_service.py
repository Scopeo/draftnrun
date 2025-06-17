import os
from typing import Generator

import pytest
from sqlalchemy import text

from engine.storage_service.db_utils import DBColumn, DBDefinition, PROCESSED_DATETIME_FIELD
from engine.storage_service.local_service import SQLLocalService
from settings import settings


TEST_SCHEMA_NAME = "test_schema"


@pytest.fixture(scope="function")
def postgres_service() -> Generator[SQLLocalService, None, None]:
    """Fixture to provide an SQLLocalService instance with PostgreSQL.

    In CI: Uses the container started by GitHub Actions
    In local dev: Uses the container from docker-compose if available
    """
    if not settings.ADA_DB_URL:
        pytest.fail("settings.ADA_DB_URL is not set")
    engine_url = settings.ADA_DB_URL
    try:
        service = SQLLocalService(engine_url=engine_url)

        # Clean up and recreate test schema for each test
        with service.engine.connect() as conn:
            conn.execute(text(f"DROP SCHEMA IF EXISTS {TEST_SCHEMA_NAME} CASCADE"))
            conn.commit()
        service.create_schema(TEST_SCHEMA_NAME)

        yield service
    except Exception as e:
        if not os.getenv("CI"):
            pytest.skip(
                "PostgreSQL test container not available. Run 'docker-compose up postgres_test' first.",
            )
        raise e


@pytest.fixture(scope="function")
def sqlite_service():
    """Fixture to provide an SQLLocalService instance with SQLite in-memory."""
    engine_url = "sqlite:///:memory:"
    service = SQLLocalService(engine_url=engine_url)
    yield service


@pytest.fixture(scope="function")
def sample_table_definition():
    """Fixture to provide a sample table definition."""
    return DBDefinition(
        columns=[
            DBColumn(name=PROCESSED_DATETIME_FIELD, type="STRING", default="CURRENT_TIMESTAMP", is_nullable=False),
            DBColumn(name="id", type="INTEGER", is_primary=True),
            DBColumn(name="name", type="STRING"),
            DBColumn(name="created_at", type="STRING"),
        ]
    )
