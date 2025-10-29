import logging
from pathlib import Path
from typing import Optional, Type, Dict, Any

import sqlalchemy
from sqlalchemy import MetaData, text, create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.sql.type_api import TypeEngine
import pandas as pd

from engine.agent.agent import ComponentAttributes
from engine.storage_service.db_service import DBService
from engine.storage_service.db_utils import (
    DBDefinition,
    check_columns_matching_between_data_and_database_table,
    PROCESSED_DATETIME_FIELD,
    CHUNK_ID_COLUMN,
)

LOGGER = logging.getLogger(__name__)

SQL_INTEGRATION_DIR = Path(__file__).parent.resolve()

TYPE_MAPPING: dict[str, Type[TypeEngine]] = {
    "STRING": sqlalchemy.String,
    "VARCHAR": sqlalchemy.String,
    "TEXT": sqlalchemy.Text,
    "TIMESTAMP": sqlalchemy.TIMESTAMP,
    "DATETIME": sqlalchemy.DateTime,
    "INTEGER": sqlalchemy.Integer,
    "FLOAT": sqlalchemy.Float,
    "BOOLEAN": sqlalchemy.Boolean,
    "ARRAY": sqlalchemy.JSON,
    "VARIANT": sqlalchemy.JSON,
}
DEFAULT_MAPPING = {"CURRENT_TIMESTAMP": sqlalchemy.func.current_timestamp()}


class SQLLocalService(DBService):
    def __init__(self, engine_url: str, component_attributes: Optional[ComponentAttributes] = None):
        super().__init__(component_attributes=component_attributes)

        self.engine = create_engine(
            engine_url,
            pool_pre_ping=True,
            pool_recycle=3600,
            connect_args={
                "connect_timeout": 5,
                "login_timeout": 5,
                "network_timeout": 5,
            },
        )
        self.metadata = MetaData()

        try:
            self.metadata.reflect(bind=self.engine)
            LOGGER.info(f"Successfully connected to database: {self.engine.url.database}")
        except Exception as e:
            error_msg = f"Failed to connect to database with engine_url. Error: {str(e)}"
            LOGGER.error(error_msg)
            raise ConnectionError(error_msg) from e

        self.Session = sessionmaker(bind=self.engine)
        self.database_name = self.engine.url.database

    def get_table(self, table_name: str, schema_name: Optional[str] = None) -> sqlalchemy.Table:
        """
        Get the SQLAlchemy Table object for the given table name.
        Raises ValueError if the table does not exist.
        """
        table_name = table_name.lower()
        if not self.table_exists(table_name, schema_name):
            raise ValueError(f"Table '{table_name}' in schema '{schema_name}' does not exist.")
        return sqlalchemy.Table(table_name, self.metadata, autoload_with=self.engine, schema=schema_name)

    def table_exists(self, table_name: str, schema_name: Optional[str] = None) -> bool:
        table_name = table_name.lower()
        inspector = sqlalchemy.inspect(self.engine)
        return inspector.has_table(table_name, schema=schema_name)

    @staticmethod
    def add_processed_datetime_if_exists(
        table: sqlalchemy.Table,
        update_values: Dict[str, Any],
    ) -> Dict[str, Any]:
        column_names = [col.name for col in table.columns]
        if PROCESSED_DATETIME_FIELD in column_names:
            update_values[PROCESSED_DATETIME_FIELD] = sqlalchemy.func.current_timestamp()
        return update_values

    @staticmethod
    def convert_table_definition_to_sqlalchemy(
        table_definition: DBDefinition,
        type_mapping: Optional[dict[str, Type[TypeEngine]]] = None,
        default_mapping: Optional[dict] = None,
    ) -> list[sqlalchemy.Column]:
        if type_mapping is None:
            type_mapping = TYPE_MAPPING
        if default_mapping is None:
            default_mapping = DEFAULT_MAPPING
        columns: list[sqlalchemy.Column] = []
        for col in table_definition.columns:
            col_type = type_mapping[col.type]
            default = None
            if col.default is not None and col.default in default_mapping:
                default = default_mapping[col.default]
            columns.append(
                sqlalchemy.Column(
                    col.name,
                    col_type,
                    primary_key=col.is_primary,
                    server_default=default,
                )
            )
        return columns

    def create_table(
        self,
        table_name: str,
        table_definition: DBDefinition,
        replace_if_exists: bool = False,
        schema_name: Optional[str] = None,
    ):
        table_name = table_name.lower()
        if replace_if_exists and self.table_exists(table_name, schema_name):
            self.drop_table(table_name, schema_name)

        if schema_name and not self.schema_exists(schema_name):
            self.create_schema(schema_name)

        if not self.table_exists(table_name, schema_name):
            columns = self.convert_table_definition_to_sqlalchemy(table_definition)
            table = sqlalchemy.Table(table_name, sqlalchemy.MetaData(), *columns, schema=schema_name)
            LOGGER.info(f"Creating table {table_name} in schema {schema_name}")
            table.create(self.engine)

    def create_schema(self, schema_name: str):
        with self.engine.connect() as conn:
            conn.execute(sqlalchemy.text(f"CREATE SCHEMA IF NOT EXISTS {schema_name}"))
            conn.commit()

    def schema_exists(self, schema_name: str) -> bool:
        query = sqlalchemy.text(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.schemata
                WHERE schema_name = :schema_name
            )
        """
        )
        with self.engine.connect() as connection:
            result = connection.execute(query, {"schema_name": schema_name}).scalar()
            return result is True

    def drop_table(
        self,
        table_name: str,
        schema_name: Optional[str] = None,
    ):
        table_name = table_name.lower()
        table = self.get_table(table_name, schema_name)
        LOGGER.info(f"Dropping table {table_name} from schema {schema_name}")
        table.drop(self.engine)

    def get_table_df(
        self,
        table_name: str,
        schema_name: Optional[str] = None,
        sql_query_filter: Optional[str] = None,
    ) -> pd.DataFrame:
        table = self.get_table(table_name, schema_name)
        with self.Session() as session:
            stmt = sqlalchemy.select(table)
            if sql_query_filter:
                stmt = stmt.where(text(sql_query_filter))
            result = session.execute(stmt)
            return pd.DataFrame(result.fetchall(), columns=result.keys())

    def describe_table(self, table_name: str, schema_name: Optional[str] = None) -> list[dict]:
        table_name = table_name.lower()
        if not self.table_exists(table_name, schema_name):
            raise ValueError(f"Table {table_name} in schema {schema_name} does not exist")
        inspector = sqlalchemy.inspect(self.engine)
        # Convert ReflectedColumn objects to dictionaries
        return [
            {
                "name": column["name"],
                "type": str(column["type"]),
                "nullable": column["nullable"],
                "default": column["default"],
                "autoincrement": column.get(
                    "autoincrement", False
                ),  # .get since autoincrement might not always be present
                "primary_key": column.get("primary_key", 0),  # .get since primary_key might not always be present
            }
            for column in inspector.get_columns(table_name, schema=schema_name)
        ]

    def upsert_value(
        self,
        table_name: str,
        id_column_name: str,
        id: str,
        values: dict,
        schema_name: Optional[str] = None,
    ) -> None:
        table = self.get_table(table_name, schema_name)
        with self.Session() as session:
            existing_record = session.execute(
                sqlalchemy.select(table).where(table.c[id_column_name] == id)
            ).scalar_one_or_none()

            if existing_record:
                # For updates, explicitly set _processed_datetime to current timestamp
                update_values = values.copy()
                update_values = self.add_processed_datetime_if_exists(table, update_values)
                stmt = sqlalchemy.update(table).where(table.c[id_column_name] == id).values(**update_values)
                session.execute(stmt)
            else:
                to_insert = {id_column_name: id, **values}
                stmt = table.insert().values(**to_insert)
                session.execute(stmt)

            session.commit()

    def insert_data(
        self,
        table_name: str,
        data: dict,
        schema_name: Optional[str] = None,
        array_columns: Optional[list] = None,
    ):
        table = self.get_table(table_name, schema_name)
        description_table = self.describe_table(table_name, schema_name)
        columns_data = list(data.keys())
        check_columns_matching_between_data_and_database_table(columns_data, description_table)
        with self.Session() as session:
            stmt = table.insert().values(**data)
            session.execute(stmt)
            session.commit()

    def insert_df_to_table(
        self,
        df: pd.DataFrame,
        table_name: str,
        schema_name: Optional[str] = None,
    ):
        # Skip if dataframe is empty
        if df.empty:
            LOGGER.info("Empty DataFrame provided, skipping insert")
            return
        table = self.get_table(table_name, schema_name)
        description_table = self.describe_table(table_name, schema_name)
        check_columns_matching_between_data_and_database_table(df.columns, description_table)

        with self.Session() as session:
            data = df.to_dict(orient="records")
            session.execute(table.insert(), data)
            session.commit()

    def grant_select_on_table(
        self,
        table_name: str,
        role: str,
        schema_name: Optional[str] = None,
    ):
        LOGGER.warning("Granting privileges is database-dependent; consider abstracting this functionality.")
        qualified_table_name = f"{schema_name}.{table_name.lower()}" if schema_name else table_name.lower()
        self._execute_query(f"GRANT SELECT ON {qualified_table_name} TO {role}")

    def _fetch_sql_query_as_dataframe(self, query: str) -> pd.DataFrame:
        return pd.read_sql(query, self.engine)

    def _refresh_table_from_df(
        self,
        df: pd.DataFrame,
        table_name: str,
        id_column: str,
        table_definition: DBDefinition,
        schema_name: Optional[str] = None,
    ) -> None:
        """
        Update a table based on the `id_column` column.
        It only updates ids that already exist in the table.
        df is the DataFrame with ONLY the updated values.
        """
        table = self.get_table(table_name, schema_name)
        sql_alchemy_columns = self.convert_table_definition_to_sqlalchemy(table_definition)

        # Remove the temporary table if it exists in metadata
        if "updated_values" in self.metadata.tables:
            self.metadata.remove(self.metadata.tables["updated_values"])

        # Create new temporary table
        temp_table = sqlalchemy.Table("updated_values", self.metadata, *sql_alchemy_columns)

        try:
            # Drop the table if it exists in the database
            temp_table.drop(self.engine, checkfirst=True)
            temp_table.create(self.engine)
            LOGGER.info(f"Temporary table created to update {table_name}")

            with self.Session() as session:
                session.execute(temp_table.insert(), df.to_dict(orient="records"))
                session.commit()

            # Exclude _processed_datetime field from the temp table values, but set it explicitly to current timestamp
            columns_to_update = {
                col.name: temp_table.c[col.name] for col in table.columns if col.name != PROCESSED_DATETIME_FIELD
            }

            columns_to_update = self.add_processed_datetime_if_exists(table, columns_to_update)

            update_stmt = table.update().where(table.c[id_column] == temp_table.c[id_column]).values(columns_to_update)

            with self.Session() as session:
                session.execute(update_stmt)
                session.commit()
        finally:
            # Always try to drop the temporary table and remove it from metadata
            try:
                temp_table.drop(self.engine, checkfirst=True)
                self.metadata.remove(temp_table)
            except Exception as e:
                LOGGER.warning(f"Failed to cleanup temporary table: {str(e)}")

    def delete_rows_from_table(
        self,
        table_name: str,
        ids: list[str | int],
        schema_name: Optional[str] = None,
        id_column_name: str = CHUNK_ID_COLUMN,
    ):
        table = self.get_table(table_name, schema_name)
        with self.Session() as session:
            delete_stmt = sqlalchemy.delete(table).where(table.c[id_column_name].in_(ids))
            session.execute(delete_stmt)
            session.commit()

    def _execute_query(self, query: str):
        with self.engine.connect() as connection:
            with connection.begin() as transaction:
                connection.execute(sqlalchemy.text(query))
                transaction.commit()

    def get_db_description(
        self,
        schema_name: Optional[str] = None,
        table_names: Optional[list[str]] = None,
    ) -> str:
        if table_names is None:
            LOGGER.info("No table names provided. Describing all tables.")
            table_names = list(self.metadata.tables.keys())

        if not table_names:
            return "No tables found to describe."

        LOGGER.info(f"Describing tables: {table_names}")
        inspector = sqlalchemy.inspect(self.engine)
        db_description = ""
        for table_name in table_names:
            table = self.get_table(table_name, schema_name)
            db_description += f"Table {table.name} has columns: "
            column_details = [f"{column.name} ({column.type})" for column in table.columns]
            db_description += f"{', '.join(column_details)}"
            foreign_keys = inspector.get_foreign_keys(table_name)
            if foreign_keys:
                db_description += " and foreign keys: "
                fk_details = [
                    f"{fk['constrained_columns']}->{fk['referred_table']}.{fk['referred_columns']}"
                    for fk in foreign_keys
                ]
                db_description += f"{', '.join(fk_details)}\n"
            db_description += (
                "This is the first row of the table: "
                + self.get_markdown_sample(table_name, schema_name=schema_name)
                + "\n"
            )
        return db_description

    def get_markdown_sample(self, table_name: str, schema_name: Optional[str] = None, sample_size: int = 1) -> str:
        table = self.get_table(table_name, schema_name)
        with self.Session() as session:
            stmt = sqlalchemy.select(table).limit(sample_size)
            result = session.execute(stmt)
            df = pd.DataFrame(result.fetchall(), columns=result.keys())
            return df.to_markdown(index=False)

    def update_row(
        self,
        table_name: str,
        chunk_id: str,
        update_data: dict,
        schema_name: Optional[str] = None,
    ) -> None:
        """
        Update a specific row in the table by its chunk_id.
        """
        table = self.get_table(table_name, schema_name)

        with self.Session() as session:
            # Check if the row exists
            existing_record = session.execute(
                sqlalchemy.select(table).where(table.c[CHUNK_ID_COLUMN] == chunk_id)
            ).scalar_one_or_none()

            if not existing_record:
                raise ValueError(f"Row with chunk_id='{chunk_id}' not found in table {table_name}")

            # Update the row
            update_values = update_data.copy()
            update_values = self.add_processed_datetime_if_exists(table, update_values)

            stmt = sqlalchemy.update(table).where(table.c.chunk_id == chunk_id).values(**update_values)
            result = session.execute(stmt)

            if result.rowcount == 0:
                raise ValueError(f"Failed to update row with chunk_id='{chunk_id}'")

            session.commit()
            LOGGER.info(f"Successfully updated row chunk_id='{chunk_id}' in table {table_name}")

    def run_query(self, query: str) -> pd.DataFrame:

        query = query.strip()
        if query.lower().startswith("insert"):
            LOGGER.info(f"Running insert query: {query}")
            with self.engine.begin() as conn:
                result = conn.execute(text(query.strip()))
                return pd.DataFrame([{"number_of_rows_inserted": result.rowcount}])
        LOGGER.info(f"Running query: {query}")
        return pd.read_sql(query, self.engine)

    def get_rows_paginated(
        self, table_name: str, schema_name: Optional[str] = None, page: int = 1, page_size: int = 10
    ) -> tuple[list[dict], int]:
        """
        Get paginated rows from a table as a list of dictionaries.
        Returns (rows, total_count) without using DataFrames.
        """
        table = self.get_table(table_name, schema_name)

        with self.Session() as session:
            # Get total count
            count_stmt = sqlalchemy.select(sqlalchemy.func.count()).select_from(table)
            total_count = session.execute(count_stmt).scalar()

            # Get paginated rows
            offset = (page - 1) * page_size
            stmt = sqlalchemy.select(table).offset(offset).limit(page_size)
            rows = session.execute(stmt).fetchall()

            result = []
            for row in rows:
                # Convert SQLAlchemy Row to dictionary
                row_dict = {}
                for column in table.columns:
                    row_dict[column.name] = getattr(row, column.name)
                result.append(row_dict)

        return result, total_count

    def get_row_by_id(
        self,
        table_name: str,
        chunk_id: str,
        schema_name: Optional[str] = None,
        id_column_name: str = CHUNK_ID_COLUMN,
    ) -> dict:
        table = self.get_table(table_name, schema_name)
        with self.Session() as session:
            stmt = sqlalchemy.select(table).where(table.c[id_column_name] == chunk_id)
            result = session.execute(stmt).fetchone()

            if result is None:
                raise ValueError(f"Row with {id_column_name}='{chunk_id}' not found in table {table_name}")

            # Convert the SQLAlchemy Row to a dictionary
            row_dict = {}
            for column in table.columns:
                row_dict[column.name] = getattr(result, column.name)

            return row_dict
