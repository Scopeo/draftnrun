from abc import ABC, abstractmethod
import logging
from typing import Optional

import pandas as pd

from engine.agent.agent import ComponentAttributes
from engine.storage_service.db_utils import DBDefinition, convert_to_correct_pandas_type


LOGGER = logging.getLogger(__name__)


class DBService(ABC):
    def __init__(self, dialect: Optional[str] = None, component_attributes: Optional[ComponentAttributes] = None):
        self.dialect = dialect
        self.component_attributes = component_attributes or ComponentAttributes(
            component_instance_name=self.__class__.__name__,
        )

    @abstractmethod
    def table_exists(self, table_name: str, schema_name: Optional[str] = None) -> bool:
        pass

    @abstractmethod
    def create_table(
        self,
        table_name: str,
        table_definition: DBDefinition,
        replace_if_exists: bool = False,
        schema_name: Optional[str] = None,
    ):
        pass

    @abstractmethod
    def create_schema(self, schema_name: Optional[str] = None):
        pass

    @abstractmethod
    def schema_exists(self, schema_name: Optional[str] = None) -> bool:
        pass

    @abstractmethod
    def drop_table(self, table_name: str, schema_name: Optional[str] = None):
        pass

    @abstractmethod
    def get_table_df(
        self,
        table_name: str,
        schema_name: Optional[str] = None,
        sql_query_filter: Optional[str] = None,
    ) -> pd.DataFrame:
        pass

    @abstractmethod
    def describe_table(self, table_name: str, schema_name: Optional[str] = None) -> list[dict]:
        """
        Return a list of dict with the columns description of the table
        [{"name": column_name, "type": column_type, ...}, ...]
        """
        pass

    @abstractmethod
    def insert_data(
        self, table_name: str, data: dict, schema_name: Optional[str] = None, array_columns: Optional[list] = None
    ):
        """Inserts data into the specified table. Handles array columns separately."""
        pass

    @abstractmethod
    def insert_df_to_table(self, df: pd.DataFrame, table_name: str, schema_name: Optional[str] = None) -> None:
        pass

    @abstractmethod
    def grant_select_on_table(
        self,
        table_name: str,
        role: str,
        schema_name: Optional[str] = None,
    ) -> None:
        pass

    def update_table(
        self,
        new_df: pd.DataFrame,
        table_name: str,
        table_definition: DBDefinition,
        id_column_name: str,
        schema_name: Optional[str] = None,
        timestamp_column_name: Optional[str] = None,
        sql_query_filter: Optional[str] = None,
    ) -> None:
        """
        Update a table on Database with a new DataFrame.
        If the table does not exist, it will be created.
        """
        if schema_name:
            target_table_name = f"{schema_name}.{table_name}"
        else:
            target_table_name = table_name

        if not self.table_exists(table_name, schema_name=schema_name):
            LOGGER.info(f"Table {target_table_name} does not exist. Creating it...")
            self.create_table(
                table_name=table_name,
                table_definition=table_definition,
                schema_name=schema_name,
            )
            # Convert pandas NaT to None for datetime-like columns before insert
            for col in new_df.select_dtypes(include=["datetime64[ns]", "datetimetz"]):
                new_df[col] = new_df[col].astype(object).where(new_df[col].notna(), None)
            self.insert_df_to_table(df=new_df, table_name=table_name, schema_name=schema_name)
        else:
            query = (
                f"SELECT {id_column_name}, {timestamp_column_name} FROM {target_table_name}"
                if timestamp_column_name
                else f"SELECT {id_column_name} FROM {target_table_name}"
            )
            final_query = f"{query} WHERE {sql_query_filter};" if sql_query_filter else f"{query};"
            old_df = self._fetch_sql_query_as_dataframe(final_query)
            old_df = convert_to_correct_pandas_type(old_df, id_column_name, table_definition)

            ids_to_delete = set(old_df[id_column_name]) - set(new_df[id_column_name])
            if ids_to_delete:
                self.delete_rows_from_table(
                    table_name=table_name,
                    ids=list(ids_to_delete),
                    id_column_name=id_column_name,
                    schema_name=schema_name,
                )
                LOGGER.info(f"Deleted {len(ids_to_delete)} rows from the table")

            # Find latest timestamp in old database and get new/updated records
            if timestamp_column_name and len(old_df) > 0:
                latest_timestamp = old_df[timestamp_column_name].max()
                LOGGER.info(f"Latest timestamp in database: {latest_timestamp}")

                # Find records with timestamps newer than the latest in database
                new_data_to_sync = new_df[new_df[timestamp_column_name] >= latest_timestamp]

                if len(new_data_to_sync) > 0:
                    ids_to_add = set(new_data_to_sync[id_column_name])
                    existing_ids = ids_to_add.intersection(set(old_df[id_column_name]))

                    # Delete existing records with these IDs first
                    if existing_ids:
                        self.delete_rows_from_table(
                            table_name=table_name,
                            ids=list(existing_ids),
                            id_column_name=id_column_name,
                            schema_name=schema_name,
                        )
                        LOGGER.info(f"Deleted {len(existing_ids)} existing rows for update")

                    # Add all newer records (both new and updated ones)
                    new_data_to_sync = new_data_to_sync.copy()
                    for col in new_data_to_sync.select_dtypes(include=["datetime64[ns]", "datetimetz"]):
                        new_data_to_sync[col] = (
                            new_data_to_sync[col].astype(object).where(new_data_to_sync[col].notna(), None)
                        )
                    self.insert_df_to_table(new_data_to_sync, table_name, schema_name=schema_name)
                    LOGGER.info(f"Added {len(new_data_to_sync)} records with timestamps newer than {latest_timestamp}")
            else:
                # If no timestamp column or empty old_df, add all new records
                incoming_ids = set(new_df[id_column_name])
                existing_ids = set(old_df[id_column_name]) if len(old_df) > 0 else set()
                new_ids_to_add = incoming_ids - existing_ids

                if new_ids_to_add:
                    new_data = new_df[new_df[id_column_name].isin(new_ids_to_add)].copy()
                    for col in new_data.select_dtypes(include=["datetime64[ns]", "datetimetz"]):
                        new_data[col] = new_data[col].astype(object).where(new_data[col].notna(), None)
                    self.insert_df_to_table(new_data, table_name, schema_name=schema_name)
                    LOGGER.info(f"Added {len(new_ids_to_add)} new rows to table")

    @abstractmethod
    def _refresh_table_from_df(
        self,
        df: pd.DataFrame,
        table_name: str,
        id_column: str,
        table_definition: DBDefinition,
        schema_name: Optional[str] = None,
    ) -> None:
        pass

    @abstractmethod
    def _fetch_sql_query_as_dataframe(self, query: str) -> pd.DataFrame:
        pass

    @abstractmethod
    def delete_rows_from_table(
        self,
        table_name: str,
        ids: list[str | int],
        id_column_name: str = "FILE_ID",
        schema_name: Optional[str] = None,
    ):
        pass

    @abstractmethod
    def get_db_description(self, schema_name: Optional[str] = None, table_names: Optional[list[str]] = None) -> str:
        pass

    @abstractmethod
    def run_query(self, query: str):
        pass

    @abstractmethod
    def upsert_value(
        self,
        table_name: str,
        id_column_name: str,
        id: str,
        values: dict,
        schema_name: Optional[str] = None,
    ) -> None:
        pass
