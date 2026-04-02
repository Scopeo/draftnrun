import asyncio
from unittest.mock import patch

import pytest

from engine.storage_service.local_service import SQLLocalService
from tests.mocks.db_service import TEST_SCHEMA_NAME


def test_create_table(postgres_service, sample_table_definition):
    postgres_service.create_table(
        "test_table",
        table_definition=sample_table_definition,
        schema_name=TEST_SCHEMA_NAME,
    )
    assert postgres_service.table_exists("test_table", TEST_SCHEMA_NAME)


def test_insert_data(postgres_service, sample_table_definition):
    postgres_service.create_table(
        "test_table",
        table_definition=sample_table_definition,
        schema_name=TEST_SCHEMA_NAME,
    )
    postgres_service.insert_data(
        "test_table",
        schema_name=TEST_SCHEMA_NAME,
        data={
            "chunk_id": 1,
            "name": "Alice",
            "created_at": "2021-01-01 11:10:00",
        },
    )
    rows = postgres_service.get_table_rows("test_table", TEST_SCHEMA_NAME)
    assert len(rows) == 1
    assert rows[0]["name"] == "Alice"


def test_insert_rows(postgres_service, sample_table_definition):
    postgres_service.create_table(
        "test_table",
        table_definition=sample_table_definition,
        schema_name=TEST_SCHEMA_NAME,
    )
    postgres_service.insert_rows(
        [
            {"chunk_id": 1, "name": "Alice", "created_at": "2021-01-01 11:10:00"},
            {"chunk_id": 2, "name": "Bob", "created_at": "2021-01-01 11:10:00"},
        ],
        "test_table",
        TEST_SCHEMA_NAME,
    )
    rows = postgres_service.get_table_rows("test_table", TEST_SCHEMA_NAME)
    assert len(rows) == 2
    assert {r["name"] for r in rows} == {"Alice", "Bob"}


def test_insert_rows_empty(postgres_service, sample_table_definition):
    postgres_service.create_table(
        "test_table",
        table_definition=sample_table_definition,
        schema_name=TEST_SCHEMA_NAME,
    )
    postgres_service.insert_rows([], "test_table", TEST_SCHEMA_NAME)
    rows = postgres_service.get_table_rows("test_table", TEST_SCHEMA_NAME)
    assert len(rows) == 0


def test_delete_rows_from_table(postgres_service, sample_table_definition):
    postgres_service.create_table(
        "test_table",
        table_definition=sample_table_definition,
        schema_name=TEST_SCHEMA_NAME,
    )
    postgres_service.insert_rows(
        [
            {"chunk_id": 1, "name": "Alice", "created_at": "2021-01-01 11:10:00"},
            {"chunk_id": 2, "name": "Bob", "created_at": "2021-01-01 11:10:00"},
        ],
        "test_table",
        schema_name=TEST_SCHEMA_NAME,
    )
    postgres_service.delete_rows_from_table(
        table_name="test_table",
        schema_name=TEST_SCHEMA_NAME,
        ids=[1],
    )
    rows = postgres_service.get_table_rows("test_table", schema_name=TEST_SCHEMA_NAME)
    assert len(rows) == 1
    assert rows[0]["name"] == "Bob"


def test_drop_table(postgres_service, sample_table_definition):
    postgres_service.create_table(
        "test_table",
        table_definition=sample_table_definition,
        schema_name=TEST_SCHEMA_NAME,
    )
    postgres_service.drop_table("test_table", schema_name=TEST_SCHEMA_NAME)
    assert not postgres_service.table_exists("test_table", schema_name=TEST_SCHEMA_NAME)


def test_get_table_rows_no_table(postgres_service):
    with pytest.raises(ValueError, match="Table 'non_existent_table' in schema 'test_schema' does not exist."):
        postgres_service.get_table_rows("non_existent_table", schema_name=TEST_SCHEMA_NAME)


def test_describe_table(postgres_service, sample_table_definition):
    postgres_service.create_table(
        "test_table",
        table_definition=sample_table_definition,
        schema_name=TEST_SCHEMA_NAME,
    )
    description = postgres_service.describe_table("test_table", schema_name=TEST_SCHEMA_NAME)
    assert len(description) == len(sample_table_definition.columns)
    assert {col["name"] for col in description} == {col.name for col in sample_table_definition.columns}


def test_fetch_sql_query_as_dicts(postgres_service, sample_table_definition):
    postgres_service.create_table(
        "test_table",
        table_definition=sample_table_definition,
        schema_name=TEST_SCHEMA_NAME,
    )
    postgres_service.insert_rows(
        [{"chunk_id": 1, "name": "Alice", "created_at": "2021-01-01 11:10:00"}],
        "test_table",
        TEST_SCHEMA_NAME,
    )
    result = postgres_service._fetch_sql_query_as_dicts(
        f"SELECT chunk_id, name FROM {TEST_SCHEMA_NAME}.test_table;"
    )
    assert len(result) == 1
    assert result[0]["name"] == "Alice"


def test_error_when_inserting_new_column(postgres_service, sample_table_definition):
    postgres_service.create_table(
        "test_table",
        table_definition=sample_table_definition,
        schema_name=TEST_SCHEMA_NAME,
    )
    with pytest.raises(ValueError):
        postgres_service.insert_rows(
            [{"chunk_id": 2, "name": "value4", "created_at": "2024-12-12 11:45:45", "metadata": "tag"}],
            table_name="test_table",
            schema_name=TEST_SCHEMA_NAME,
        )
    with pytest.raises(ValueError):
        postgres_service.insert_data(
            "test_table",
            data={"chunk_id": 1, "name": "value2", "created_at": "2024-12-10 11:45:45", "metadata": "tag"},
            schema_name=TEST_SCHEMA_NAME,
        )


def test_sql_local_service_reuses_engine_pool_per_url_postgres(postgres_service):
    for cached in SQLLocalService._engine_cache.values():
        cached["engine"].dispose()
    SQLLocalService._engine_cache.clear()

    engine_url = str(postgres_service.engine.url)
    service_a = SQLLocalService(engine_url=engine_url)
    service_b = SQLLocalService(engine_url=engine_url)

    assert service_a.engine is service_b.engine
    assert SQLLocalService._engine_cache[engine_url]["ref_count"] == 2

    shared_engine = service_a.engine

    asyncio.run(service_a.close())
    assert SQLLocalService._engine_cache[engine_url]["ref_count"] == 1

    with patch.object(shared_engine, "dispose", wraps=shared_engine.dispose) as mock_dispose:
        asyncio.run(service_b.close())
        assert engine_url not in SQLLocalService._engine_cache
        mock_dispose.assert_called_once()
