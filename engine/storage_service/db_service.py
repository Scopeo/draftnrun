from abc import ABC, abstractmethod
import logging
from typing import Optional

import pandas as pd

from engine.storage_service.db_utils import DBDefinition, convert_to_correct_pandas_type


LOGGER = logging.getLogger(__name__)


class DBService(ABC):
    def __init__(self, dialect: Optional[str] = None):
        self.dialect = dialect

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
    def get_table_df(self, table_name: str, schema_name: Optional[str] = None) -> pd.DataFrame:
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
        append_mode: bool = True,
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
        else:  # Update existing table
            query = (
                f"SELECT {id_column_name}, {timestamp_column_name} FROM {target_table_name};"
                if timestamp_column_name
                else f"SELECT {id_column_name} FROM {target_table_name};"
            )
            old_df = self._fetch_sql_query_as_dataframe(query)
            old_df = convert_to_correct_pandas_type(old_df, id_column_name, table_definition)

            common_df = new_df.merge(old_df, on=id_column_name, how="inner")
            if timestamp_column_name:
                ids_to_update = set(
                    common_df[common_df[timestamp_column_name + "_x"] > common_df[timestamp_column_name + "_y"]][
                        id_column_name
                    ]
                )
            else:
                ids_to_update = set(common_df[id_column_name])
            LOGGER.info(f"Found {len(ids_to_update)} rows to update in the table")
            updated_data = new_df[new_df[id_column_name].isin(ids_to_update)].copy()
            self._refresh_table_from_df(
                df=updated_data,
                table_name=table_name,
                id_column=id_column_name,
                table_definition=table_definition,
                schema_name=schema_name,
            )

            new_df["exists"] = new_df[id_column_name].isin(old_df[id_column_name].values)
            LOGGER.info(f"Found {new_df['exists'][new_df['exists']].sum()} existing rows in the table")
            new_data = new_df[~new_df["exists"]].copy()
            new_data.drop(columns=["exists"], inplace=True)
            self.insert_df_to_table(new_data, table_name, schema_name=schema_name)

            if not append_mode:
                ids_to_delete = set(old_df[id_column_name]) - set(new_df[id_column_name])
                LOGGER.info(f"Found {len(ids_to_delete)} rows to delete in the table")
                if len(ids_to_delete) > 0:
                    self.delete_rows_from_table(
                        table_name=table_name,
                        ids=list(ids_to_delete),
                        id_column_name=id_column_name,
                        schema_name=schema_name,
                    )

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
