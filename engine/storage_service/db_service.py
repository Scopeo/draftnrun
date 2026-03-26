import logging
from abc import ABC, abstractmethod
from typing import Any, Callable, Iterator, Optional

import pandas as pd

from engine.components.close_mixin import CloseMixin
from engine.components.component import ComponentAttributes
from engine.datetime_utils import make_naive_utc, parse_datetime
from engine.storage_service.db_utils import CHUNK_ID_COLUMN, DBDefinition, cast_id_value
from settings import settings

LOGGER = logging.getLogger(__name__)


class DBService(CloseMixin, ABC):
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
    def get_table_df(self, table_name: str, schema_name: Optional[str] = None, sql_query_filter: Optional[str] = None):
        pass

    @abstractmethod
    def iter_table_rows(
        self,
        table_name: str,
        batch_size: Optional[int] = None,
        schema_name: Optional[str] = None,
        sql_query_filter: Optional[str] = None,
    ) -> Iterator[list[dict]]:
        """Yield batches of rows as list[dict]."""
        pass

    @abstractmethod
    def get_column_values(
        self,
        table_name: str,
        columns: list[str],
        schema_name: Optional[str] = None,
        sql_query_filter: Optional[str] = None,
    ) -> list[dict]:
        """Return rows containing only the specified columns."""
        pass

    @abstractmethod
    def get_rows_by_ids(
        self,
        table_name: str,
        chunk_ids: list[str],
        schema_name: Optional[str] = None,
        id_column_name: str = CHUNK_ID_COLUMN,
        sql_query_filter: Optional[str] = None,
    ) -> list[dict]:
        """Get multiple rows by their chunk IDs."""
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
    def insert_rows(
        self, rows: list[dict], table_name: str, schema_name: Optional[str] = None, batch_size: Optional[int] = None
    ) -> None:
        """Insert a list of row dicts into a table. If batch_size is set, inserts in batches."""
        pass

    def insert_df_to_table(self, df, table_name: str, schema_name: Optional[str] = None) -> None:
        """Convenience method that accepts a pandas DataFrame. Prefer insert_rows."""
        if hasattr(df, "empty") and df.empty:
            return
        rows = df.to_dict(orient="records") if hasattr(df, "to_dict") else list(df)
        self.insert_rows(rows, table_name, schema_name=schema_name)

    @abstractmethod
    def grant_select_on_table(
        self,
        table_name: str,
        role: str,
        schema_name: Optional[str] = None,
    ) -> None:
        pass

    @abstractmethod
    def _fetch_column_as_set(
        self,
        table_name: str,
        column_name: str,
        schema_name: Optional[str] = None,
        source_id: Optional[str] = None,
    ) -> set:
        """
        Fetch all values from a specific column as a set.
        If source_id is provided, only fetch values for rows matching that source_id.
        """
        pass

    @abstractmethod
    def _fetch_sql_query_as_dicts(self, query: str) -> list[dict]:
        """Execute a SQL query and return the result as a list of dicts."""
        pass

    def _fetch_sql_query_as_dataframe(self, query: str):
        """Convenience method that returns a pandas DataFrame. Prefer _fetch_sql_query_as_dicts."""
        rows = self._fetch_sql_query_as_dicts(query)
        return pd.DataFrame(rows)

    def update_table(
        self,
        incoming_ids_with_timestamp: dict[str, Any],
        fetch_rows_fn: Callable[[set[str]], list[dict]],
        table_name: str,
        table_definition: DBDefinition,
        id_column_name: str,
        schema_name: Optional[str] = None,
        timestamp_column_name: Optional[str] = None,
        append_mode: bool = True,
        sql_query_filter: Optional[str] = None,
        source_id: Optional[str] = None,
        batch_size: Optional[int] = None,
    ) -> None:
        """
        Update a table with incoming data identified by IDs and timestamps.

        Accepts a lightweight dict of {id: timestamp} for diffing and a callback
        that is called only for IDs that actually need to be inserted or updated.
        Creates the table if it does not exist.
        """
        if not incoming_ids_with_timestamp:
            LOGGER.info("Empty incoming IDs provided, skipping update")
            return

        if batch_size is None:
            batch_size = settings.INGESTION_BATCH_SIZE

        target_table_name = f"{schema_name}.{table_name}" if schema_name else table_name

        def _fetch_and_insert_batched(ids: set[str]) -> None:
            id_list = list(ids)
            effective_batch_size = batch_size or len(id_list)
            for i in range(0, len(id_list), effective_batch_size):
                batch_ids = set(id_list[i : i + effective_batch_size])
                rows = fetch_rows_fn(batch_ids)
                if rows:
                    self.insert_rows(rows, table_name, schema_name=schema_name, batch_size=batch_size)

        if not self.table_exists(table_name, schema_name=schema_name):
            LOGGER.info(f"Table {target_table_name} does not exist. Creating it...")
            self.create_table(table_name=table_name, table_definition=table_definition, schema_name=schema_name)
            _fetch_and_insert_batched(set(incoming_ids_with_timestamp.keys()))
            return

        all_existing_ids = self._fetch_column_as_set(
            table_name=table_name,
            column_name=id_column_name,
            schema_name=schema_name,
            source_id=source_id,
        )

        query = (
            f"SELECT {id_column_name}, {timestamp_column_name} FROM {target_table_name}"
            if timestamp_column_name
            else f"SELECT {id_column_name} FROM {target_table_name}"
        )
        filters = []
        if source_id is not None:
            filters.append(f"source_id = '{source_id}'")
        if sql_query_filter:
            filters.append(f"({sql_query_filter})")
        final_query = f"{query} WHERE {' AND '.join(filters)};" if filters else f"{query};"
        existing_rows = self._fetch_sql_query_as_dicts(final_query)

        existing_by_id: dict = {}
        for row in existing_rows:
            row_id = cast_id_value(row[id_column_name], id_column_name, table_definition)
            existing_by_id[row_id] = row

        incoming_ids = set(incoming_ids_with_timestamp.keys())
        ids_to_add = incoming_ids - all_existing_ids
        common_ids = incoming_ids & set(existing_by_id.keys())

        if timestamp_column_name and not sql_query_filter:
            ids_to_update = set()
            for shared_id in common_ids:
                incoming_dt = parse_datetime(incoming_ids_with_timestamp[shared_id])
                existing_dt = parse_datetime(existing_by_id[shared_id].get(timestamp_column_name))
                if incoming_dt is not None and existing_dt is not None:
                    if make_naive_utc(incoming_dt) > make_naive_utc(existing_dt):
                        ids_to_update.add(shared_id)
                elif incoming_ids_with_timestamp[shared_id] != existing_by_id[shared_id].get(timestamp_column_name):
                    ids_to_update.add(shared_id)
        else:
            ids_to_update = common_ids

        ids_to_delete = set(existing_by_id.keys()) - incoming_ids if not append_mode else set()

        LOGGER.info(f"Diff: {len(ids_to_add)} to add, {len(ids_to_update)} to update, {len(ids_to_delete)} to delete")

        if ids_to_delete:
            self.delete_rows_from_table(
                table_name=table_name,
                ids=list(ids_to_delete),
                id_column_name=id_column_name,
                schema_name=schema_name,
            )

        if ids_to_update:
            self.delete_rows_from_table(
                table_name=table_name,
                ids=list(ids_to_update),
                id_column_name=id_column_name,
                schema_name=schema_name,
            )
            _fetch_and_insert_batched(ids_to_update)

        if ids_to_add:
            _fetch_and_insert_batched(ids_to_add)

    @abstractmethod
    def delete_rows_from_table(
        self,
        table_name: str,
        ids: list[str | int],
        schema_name: Optional[str] = None,
        id_column_name: str = CHUNK_ID_COLUMN,
    ):
        pass

    @abstractmethod
    def get_db_description(self, schema_name: Optional[str] = None, table_names: Optional[list[str]] = None) -> str:
        pass

    @abstractmethod
    def run_query(self, query: str) -> pd.DataFrame:
        pass

    @abstractmethod
    def upsert_value(
        self,
        table_name: str,
        id: str,
        values: dict,
        schema_name: Optional[str] = None,
        id_column_name: str = CHUNK_ID_COLUMN,
    ) -> None:
        pass

    @abstractmethod
    def update_row(
        self,
        table_name: str,
        chunk_id: str,
        update_data: dict,
        schema_name: Optional[str] = None,
    ) -> None:
        pass
