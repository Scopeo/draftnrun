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
            self.insert_df_to_table(df=new_df, table_name=table_name, schema_name=schema_name)
        else:
            # First get ids and timestamp column
            query = (
                f"SELECT {id_column_name}, {timestamp_column_name} FROM {target_table_name}"
                if timestamp_column_name
                else f"SELECT {id_column_name} FROM {target_table_name}"
            )

            final_query = f"{query} WHERE {sql_query_filter};" if sql_query_filter else f"{query};"
            old_df = self._fetch_sql_query_as_dataframe(final_query)
            old_df = convert_to_correct_pandas_type(old_df, id_column_name, table_definition)

            ids_to_delete = set(old_df[id_column_name]) - set(new_df[id_column_name])

            # Check if we should delete rows (only if less than 20% of rows are being deleted)
            if ids_to_delete and len(old_df) > 0:
                deletion_percentage = len(ids_to_delete) / len(old_df)
                if deletion_percentage <= 0.2:
                    self.delete_rows_from_table(
                        table_name=table_name,
                        ids=list(ids_to_delete),
                        id_column_name=id_column_name,
                        schema_name=schema_name,
                    )
                    old_df = old_df[~old_df[id_column_name].isin(ids_to_delete)]
                    LOGGER.info(f"Deleted {len(ids_to_delete)} rows from the table ({deletion_percentage:.1%})")
                else:
                    LOGGER.warning(
                        f"Deleting {deletion_percentage:.1%} of the rows from the table is "
                        "not allowed (max 20%). Skipping deletion."
                    )

            # find the latest timestamp for old_df
            if not old_df.empty and timestamp_column_name:
                old_df["timestamp"] = pd.to_datetime(old_df[timestamp_column_name])
                latest_timestamp = old_df["timestamp"].max()
                if pd.notna(latest_timestamp):
                    LOGGER.info(f"Latest timestamp in the table is {latest_timestamp}")
                    # take the data only >= from latest date for new_df
                    # Convert new_df timestamp column to datetime for proper comparison
                    new_df["temp_timestamp"] = pd.to_datetime(new_df[timestamp_column_name])
                    new_df = new_df[new_df["temp_timestamp"] >= latest_timestamp]
                    new_df = new_df.drop(columns=["temp_timestamp"])
                    LOGGER.info(f"Filtered new_df to {len(new_df)} rows after timestamp filter")
                else:
                    LOGGER.warning("No valid timestamps found in old_df, using all new data")
            else:
                LOGGER.info("No timestamp filtering applied")

            LOGGER.info(f"Found {len(new_df)} rows to update in the table")
            # For timestamp filtering, we need to find:
            # - ids_to_update: IDs that exist in both old_df and new_df (need to be updated with newer data)
            # - ids_to_add: IDs that exist in new_df but not in old_df (completely new)
            ids_to_update = set(new_df[id_column_name]) & set(old_df[id_column_name])
            ids_to_add = set(new_df[id_column_name]) - set(old_df[id_column_name])
            new_df_to_add = new_df[new_df[id_column_name].isin(ids_to_add)]
            new_df_to_update = new_df[new_df[id_column_name].isin(ids_to_update)]
            if not new_df_to_add.empty:
                self.insert_df_to_table(
                    df=new_df_to_add,
                    table_name=table_name,
                    schema_name=schema_name,
                )
            if not new_df_to_update.empty:
                self._refresh_table_from_df(
                    df=new_df_to_update,
                    table_name=table_name,
                    id_column=id_column_name,
                    table_definition=table_definition,
                    schema_name=schema_name,
                )
            LOGGER.info(f"Updated {len(new_df_to_update)} rows in the table")
            LOGGER.info(f"Added {len(new_df_to_add)} rows to the table")

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
