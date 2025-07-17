import logging
from typing import Optional
import threading

import pandas as pd
from snowflake.connector.pandas_tools import write_pandas

from engine.agent.data_structures import SourceChunk, ComponentAttributes
from engine.storage_service.db_service import DBService
from engine.storage_service.db_utils import DBDefinition, check_columns_matching_between_data_and_database_table
from engine.storage_service.snowflake_service.snowflake_utils import (
    connect_to_snowflake,
    dict_to_object_construct,
    escape_sql_string,
    format_json,
)

LOGGER = logging.getLogger(__name__)


class SnowflakeService(DBService):
    _lock = threading.Lock()

    def __init__(
        self,
        database_name: str,
        warehouse: str = "AIRBYTE_WAREHOUSE",
        role_to_use: str = "AIRBYTE_ROLE",
        component_attributes: Optional[ComponentAttributes] = None,
    ):
        super().__init__(dialect="snowflake sql", component_attributes=component_attributes)
        self.database_name = database_name
        self.connector = connect_to_snowflake()
        LOGGER.info(
            f"Connecting to Snowflake with {warehouse} warehouse, " f"{database_name} database and {role_to_use} role"
        )
        self.connector.cursor().execute(f"USE ROLE {role_to_use}")
        self.connector.cursor().execute(f"USE WAREHOUSE {warehouse}")
        self.connector.cursor().execute(f"USE DATABASE {database_name}")

    def schema_exists(self, schema_name: str) -> bool:
        """Check if a schema exists in the current database."""
        result = (
            self.connector.cursor()
            .execute(f"SELECT COUNT(*) FROM INFORMATION_SCHEMA.SCHEMATA WHERE SCHEMA_NAME = '{schema_name}'")
            .fetchone()
        )
        return result[0] > 0

    def create_schema(self, schema_name: str):
        if not self.schema_exists(schema_name):
            LOGGER.info(f"Schema is not exists, creating schema {schema_name}")
            self.connector.cursor().execute(f"CREATE SCHEMA IF NOT EXISTS {schema_name}")

    def delete_schema(self, schema_name: str):
        if self.schema_exists(schema_name):
            LOGGER.info(f"Deleting schema {schema_name}")
            self.connector.cursor().execute(f"DROP SCHEMA {schema_name}")

    def table_exists(self, table_name: str, schema_name: str) -> bool:
        query = f"SHOW TABLES IN SCHEMA {schema_name}"
        tables = self.connector.cursor().execute(query).fetchall()
        return any(table[1].lower() == table_name.lower() for table in tables)

    @staticmethod
    def convert_table_definition_to_string(table_definition: DBDefinition) -> str:
        formatted_column_info = []
        for column in table_definition.columns:
            column_description_str = column.name + " " + column.type
            if column.default is not None:
                column_description_str += f" DEFAULT {column.default}"
            if column.is_primary:
                column_description_str += " PRIMARY KEY"
            if not column.is_nullable and not column.is_primary:
                column_description_str += " NOT NULL"
            formatted_column_info.append(column_description_str)
        return ", ".join(formatted_column_info)

    def create_table(
        self,
        table_name: str,
        table_definition: DBDefinition,
        schema_name: str,
        replace_if_exists: bool = False,
    ):
        self.create_schema(schema_name)
        table_definition_str = self.convert_table_definition_to_string(table_definition)
        if "-" in table_name:
            raise ValueError(f"Table name {table_name} contains invalid character '-'")

        if replace_if_exists:
            self.drop_table(table_name, schema_name)

        if not self.table_exists(table_name, schema_name):
            LOGGER.info(f"Creating table {table_name} in schema {schema_name}")
            self.connector.cursor().execute(f"CREATE TABLE {schema_name}.{table_name} ({table_definition_str})")

    def drop_table(self, table_name: str, schema_name: str):
        if self.table_exists(table_name, schema_name):
            LOGGER.info(f"Dropping table {table_name}")
            self.connector.cursor().execute(f"DROP TABLE {schema_name}.{table_name}")

    def get_table_df(self, table_name: str, schema_name: str) -> pd.DataFrame:
        if not self.table_exists(table_name, schema_name):
            raise ValueError(f"Table {table_name} does not exist in schema {schema_name}")
        query = f"SELECT * FROM {schema_name}.{table_name};"
        with self._lock:
            df = self.connector.cursor().execute(query).fetch_pandas_all()

        columns_description = self.describe_table(table_name=table_name, schema_name=schema_name)
        json_columns_name = [
            column["name"] for column in columns_description if column["type"] in ["OBJECT", "VARIANT", "ARRAY"]
        ]
        for column_name in json_columns_name:
            df[column_name] = df[column_name].apply(format_json)
        df = df.rename(columns={col: col.lower() for col in df.columns})
        return df

    def describe_table(self, table_name: str, schema_name: str) -> list[dict]:
        """
        Return a list of dict with the columns description of the table
        [{"name": column_name, "type": column_type, ...}, ...]
        See https://docs.snowflake.com/en/sql-reference/sql/desc-table for more information
        """
        if not self.table_exists(table_name, schema_name):
            raise ValueError(f"Table {table_name} does not exist in schema {schema_name}")
        query = f"DESCRIBE TABLE {schema_name}.{table_name};"
        with self._lock:
            columns_description = self.connector.cursor().execute(query).fetchall()
            df_describe = pd.DataFrame(
                columns_description,
                columns=[
                    "name",
                    "type",
                    "kind",
                    "is_nullable",
                    "default",
                    "is_primary_key",
                    "unique key",
                    "check",
                    "expression",
                    "comment",
                    "policy name",
                    "privacy domain",
                ],
            )
        return df_describe.to_dict(orient="records")

    def insert_data(
        self,
        table_name: str,
        schema_name: str,
        data: dict,
        array_columns: Optional[list] = None,
    ):
        """Inserts data into the specified table. Handles array columns separately."""
        if array_columns is None:
            array_columns = []
        keys = ", ".join(data.keys())
        values = []
        df_table_description = self.describe_table(table_name, schema_name)
        check_columns_matching_between_data_and_database_table(data.keys(), df_table_description)
        for key, value in data.items():
            if key in array_columns:
                formatted_value = self.convert_list_to_sql_array(value)
            else:
                formatted_value = "'" + escape_sql_string(str(value)) + "'"
            values.append(formatted_value)
        values_clause = ", ".join(values)
        query = f"INSERT INTO {schema_name}.{table_name} ({keys}) SELECT {values_clause}"
        with self._lock:
            self.connector.cursor().execute(query)

    def insert_df_to_table(self, df: pd.DataFrame, table_name: str, schema_name: str) -> None:
        df_table_description = self.describe_table(table_name, schema_name)
        check_columns_matching_between_data_and_database_table(df.columns, df_table_description)
        write_pandas(
            self.connector,
            df,
            table_name,
            database=self.database_name,
            schema=schema_name,
            quote_identifiers=False,
        )

    def grant_select_on_table(self, table_name: str, schema_name: str, role: str) -> None:
        self.connector.cursor().execute(f"GRANT USAGE ON SCHEMA {schema_name} TO ROLE {role}")
        self.connector.cursor().execute(f"GRANT SELECT ON {schema_name}.{table_name} TO ROLE {role}")

    def _refresh_table_from_df(
        self,
        df: pd.DataFrame,
        table_name: str,
        schema_name: str,
        id_column: str,
        table_definition: DBDefinition,
    ) -> None:
        """
        Update a table on Snowflake based on the `id_column` column.
        It only updates ids that already exist in the table on Snowflake.
        df is the DataFrame with the updated values.
        """
        table_definition_str = self.convert_table_definition_to_string(table_definition)
        query_temporary = f"CREATE TEMPORARY TABLE {schema_name}.updated_values ({table_definition_str});"
        self.connector.cursor().execute(query_temporary)
        self.insert_df_to_table(
            df=df,
            table_name="updated_values",
            schema_name=schema_name,
        )
        LOGGER.info(f"Temporary table created to update {schema_name}.{table_name}")

        df.columns = [column.upper() for column in df.columns]
        query = (
            f"UPDATE {schema_name}.{table_name} SET "
            + ", ".join([f"{column} = {schema_name}.updated_values.{column}" for column in df.columns])
            + f" FROM {schema_name}.updated_values "
            + f"WHERE {schema_name}.{table_name}.{id_column} = "
            + f"{schema_name}.updated_values.{id_column};"
        )
        self.connector.cursor().execute(query)
        self.connector.cursor().execute(f"DROP TABLE {schema_name}.updated_values;")

    def _fetch_sql_query_as_dataframe(self, query: str) -> pd.DataFrame:
        with self._lock:
            df = self.connector.cursor().execute(query).fetch_pandas_all()
        df.columns = df.columns.str.lower()
        return df

    @staticmethod
    def convert_list_to_sql_array(items: list) -> str:
        """
        Convert a list of dictionaries into a SQL array instruction
        """
        if not items:
            return "ARRAY_CONSTRUCT()"

        array_elements = []
        for item in items:
            if isinstance(item, dict):
                array_elements.append(dict_to_object_construct(item))
            elif isinstance(item, SourceChunk):
                array_elements.append(dict_to_object_construct(item.model_dump()))
            elif isinstance(item, str):
                array_elements.append(f"'{escape_sql_string(item)}'")
            else:
                raise ValueError(f"Unsupported type {type(item)} for item {item}")

        return f"ARRAY_CONSTRUCT({', '.join(array_elements)})"

    def delete_rows_from_table(
        self,
        table_name: str,
        schema_name: str,
        ids: list[str | int],
        id_column_name: str = "FILE_ID",
    ):
        placeholders = ",".join(["%s"] * len(ids))
        query = f'DELETE FROM {schema_name}.{table_name} WHERE "{id_column_name}" IN ({placeholders})'
        self.connector.cursor().execute(query, ids)

    def get_db_description(
        self,
        schema_name: str,
        table_names: Optional[list[str]] = None,
    ) -> str:
        if table_names is None:
            table_info = self.connector.cursor().execute(f"SHOW TABLES in {schema_name}").fetchall()
            table_names = [table[1] for table in table_info]
        db_description = f"Snowflake database {self.database_name} and schema {schema_name}\n"

        for table_name in table_names:
            columns_description = self.describe_table(table_name=table_name, schema_name=schema_name)
            db_description += f"\nTable {table_name}: "
            column_details = [f"{column['name']} ({column['type']})" for column in columns_description]
            db_description += ", ".join(column_details)
        return db_description

    def run_query(self, query: str) -> pd.DataFrame:
        with self._lock:
            df = self.connector.cursor().execute(query).fetch_pandas_all()
        return df

    def upsert_value(self, table_name: str, id_column_name: str, id: str, values: dict, schema_name: str) -> None:
        # Construct the SET part of the SQL query
        set_clause = ", ".join([f"{column} = %s" for column in values.keys()])
        query = (
            f"INSERT INTO {schema_name}.{table_name} ({id_column_name}) VALUES (%s) "
            + f"ON CONFLICT ({id_column_name}) DO UPDATE SET {set_clause}"
        )
        with self._lock:
            self.connector.cursor().execute(query, (id,) + tuple(values.values()))
