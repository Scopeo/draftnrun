import pandas as pd
import pytest

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
            "id": 1,
            "name": "Alice",
            "created_at": "2021-01-01 11:10:00",
        },
    )
    df = postgres_service.get_table_df("test_table", TEST_SCHEMA_NAME)
    assert len(df) == 1
    assert df.iloc[0]["name"] == "Alice"


def test_insert_df_to_table(postgres_service, sample_table_definition):
    postgres_service.create_table(
        "test_table",
        table_definition=sample_table_definition,
        schema_name=TEST_SCHEMA_NAME,
    )
    df = pd.DataFrame(
        [
            {
                "id": 1,
                "name": "Alice",
                "created_at": "2021-01-01 11:10:00",
            },
            {
                "id": 2,
                "name": "Bob",
                "created_at": "2021-01-01 11:10:00",
            },
        ]
    )
    postgres_service.insert_df_to_table(df, "test_table", TEST_SCHEMA_NAME)
    result_df = postgres_service.get_table_df("test_table", TEST_SCHEMA_NAME)
    assert len(result_df) == 2
    assert set(result_df["name"]) == {"Alice", "Bob"}


def test_delete_rows_from_table(postgres_service, sample_table_definition):
    postgres_service.create_table(
        "test_table",
        table_definition=sample_table_definition,
        schema_name=TEST_SCHEMA_NAME,
    )
    df = pd.DataFrame(
        [
            {
                "id": 1,
                "name": "Alice",
                "created_at": "2021-01-01 11:10:00",
            },
            {
                "id": 2,
                "name": "Bob",
                "created_at": "2021-01-01 11:10:00",
            },
        ]
    )
    postgres_service.insert_df_to_table(df, "test_table", schema_name=TEST_SCHEMA_NAME)
    postgres_service.delete_rows_from_table(
        table_name="test_table", schema_name=TEST_SCHEMA_NAME, ids=[1], id_column_name="id"
    )
    result_df = postgres_service.get_table_df("test_table", schema_name=TEST_SCHEMA_NAME)
    assert len(result_df) == 1
    assert result_df.iloc[0]["name"] == "Bob"


def test_refresh_table(postgres_service, sample_table_definition):
    postgres_service.create_table(
        "test_table",
        table_definition=sample_table_definition,
        schema_name=TEST_SCHEMA_NAME,
    )
    df = pd.DataFrame(
        [
            {
                "id": 1,
                "name": "Alice",
                "created_at": "2021-01-01 11:10:00",
            },
            {
                "id": 2,
                "name": "Bob",
                "created_at": "2021-01-01 11:10:00",
            },
        ]
    )
    postgres_service.insert_df_to_table(df, "test_table", TEST_SCHEMA_NAME)

    updated_df = pd.DataFrame(
        [
            {
                "id": 1,
                "name": "Alice Updated",
                "created_at": "2021-02-01 11:15:00",
            }
        ]
    )
    postgres_service._refresh_table_from_df(
        df=updated_df,
        table_name="test_table",
        id_column="id",
        table_definition=sample_table_definition,
        schema_name=TEST_SCHEMA_NAME,
    )

    result_df = postgres_service.get_table_df(table_name="test_table", schema_name=TEST_SCHEMA_NAME)
    assert len(result_df) == 2
    assert result_df[result_df["id"] == 1].iloc[0]["name"] == "Alice Updated"


def test_drop_table(postgres_service, sample_table_definition):
    postgres_service.create_table(
        "test_table",
        table_definition=sample_table_definition,
        schema_name=TEST_SCHEMA_NAME,
    )
    postgres_service.drop_table("test_table", schema_name=TEST_SCHEMA_NAME)
    assert not postgres_service.table_exists("test_table", schema_name=TEST_SCHEMA_NAME)


def test_get_table_df_no_table(postgres_service):
    with pytest.raises(ValueError, match="Table 'non_existent_table' in schema 'test_schema' does not exist."):
        postgres_service.get_table_df("non_existent_table", schema_name=TEST_SCHEMA_NAME)


def test_describe_table(postgres_service, sample_table_definition):
    postgres_service.create_table(
        "test_table",
        table_definition=sample_table_definition,
        schema_name=TEST_SCHEMA_NAME,
    )
    description = postgres_service.describe_table("test_table", schema_name=TEST_SCHEMA_NAME)
    assert len(description) == len(sample_table_definition.columns)
    assert {col["name"] for col in description} == {col.name for col in sample_table_definition.columns}


def test_error_when_inserting_new_column(postgres_service, sample_table_definition):
    postgres_service.create_table(
        "test_table",
        table_definition=sample_table_definition,
        schema_name=TEST_SCHEMA_NAME,
    )
    df_to_insert = pd.DataFrame(
        [[2, "value4", "2024-12-12 11:45:45", "tag"]], columns=["id", "name", "created_at", "metadata"]
    )
    with pytest.raises(ValueError):
        postgres_service.insert_df_to_table(df_to_insert, table_name="test_table", schema_name=TEST_SCHEMA_NAME)
    with pytest.raises(ValueError):
        postgres_service.insert_data(
            "test_table",
            data={"id": 1, "name": "value2", "created_at": "2024-12-10 11:45:45", "metadata": "tag"},
            schema_name=TEST_SCHEMA_NAME,
        )
