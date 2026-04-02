import logging
from abc import ABC, abstractmethod
from typing import Any, Callable, Iterator, Optional

import pandas as pd

from engine.components.close_mixin import CloseMixin
from engine.components.component import ComponentAttributes
from engine.datetime_utils import make_naive_utc, parse_datetime
from engine.storage_service.db_utils import CHUNK_ID_COLUMN, DBDefinition, cast_id_value

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
        schema_name: Optional[str] = None,
        sql_query_filter: Optional[str] = None,
    ) -> Iterator[list[dict]]:
        """Yield batches of rows as list[dict]."""
        pass

    @abstractmethod
    def fetch_selected_columns(
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
    def insert_rows(self, rows: list[dict], table_name: str, schema_name: Optional[str] = None) -> None:
        """Insert a list of row dicts into a table."""
        pass

    @abstractmethod
    def upsert_rows(
        self,
        table_name: str,
        rows: list[dict],
        schema_name: Optional[str] = None,
        id_column_names: Optional[list[str]] = None,
    ) -> None:
        """Insert rows or update them on primary key conflict."""
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

    def _fetch_and_upsert_batches(
        self,
        ids: set[str],
        fetch_rows_fn: Callable[[set[str]], list[dict]],
        table_name: str,
        schema_name: Optional[str],
        batch_size: int,
        id_column_names: Optional[list[str]] = None,
    ) -> None:
        """Fetch rows via callback and upsert them in batches.

        Uses upsert (ON CONFLICT DO UPDATE) instead of plain insert to be idempotent:
        if the process crashes mid-batch and retries, already-inserted rows are updated
        rather than causing a UniqueViolation.
        """
        id_list = list(ids)
        for i in range(0, len(id_list), batch_size):
            batch_ids = set(id_list[i : i + batch_size])
            rows = fetch_rows_fn(batch_ids)
            if rows:
                self.upsert_rows(table_name, rows, schema_name=schema_name, id_column_names=id_column_names)

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
        batch_size: int = 500,
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

        target_table_name = f"{schema_name}.{table_name}" if schema_name else table_name

        # Used by upsert_rows for ON CONFLICT — must match the composite PK (e.g. chunk_id + source_id)
        primary_key_columns = [col.name for col in table_definition.columns if col.is_primary]

        if not self.table_exists(table_name, schema_name=schema_name):
            LOGGER.info(f"Table {target_table_name} does not exist. Creating it...")
            self.create_table(table_name=table_name, table_definition=table_definition, schema_name=schema_name)
            self._fetch_and_upsert_batches(
                set(incoming_ids_with_timestamp.keys()),
                fetch_rows_fn,
                table_name,
                schema_name,
                batch_size,
                id_column_names=primary_key_columns,
            )
            return

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
        existing_id_ts_pairs = self._fetch_sql_query_as_dicts(final_query)

        existing_ids_with_ts = {
            cast_id_value(pair[id_column_name], id_column_name, table_definition): pair.get(timestamp_column_name)
            for pair in existing_id_ts_pairs
        }

        incoming_ids = set(incoming_ids_with_timestamp.keys())
        existing_ids = set(existing_ids_with_ts.keys())
        common_ids = incoming_ids & existing_ids
        ids_to_add = incoming_ids - existing_ids

        if timestamp_column_name:
            ids_to_update = set()
            for shared_id in common_ids:
                incoming_dt = parse_datetime(incoming_ids_with_timestamp[shared_id])
                existing_dt = parse_datetime(existing_ids_with_ts[shared_id])
                if incoming_dt is not None and existing_dt is not None:
                    if make_naive_utc(incoming_dt) > make_naive_utc(existing_dt):
                        ids_to_update.add(shared_id)
                elif incoming_ids_with_timestamp[shared_id] != existing_ids_with_ts[shared_id]:
                    ids_to_update.add(shared_id)
        else:
            ids_to_update = common_ids

        ids_to_delete = existing_ids - incoming_ids if not append_mode else set()

        LOGGER.info(f"Diff: {len(ids_to_add)} to add, {len(ids_to_update)} to update, {len(ids_to_delete)} to delete")

        source_id_filter = f"source_id = '{source_id}'" if source_id else None

        if ids_to_delete:
            self.delete_rows_from_table(
                table_name=table_name,
                ids=list(ids_to_delete),
                id_column_name=id_column_name,
                schema_name=schema_name,
                sql_query_filter=source_id_filter,
            )

        if ids_to_update:
            self.delete_rows_from_table(
                table_name=table_name,
                ids=list(ids_to_update),
                id_column_name=id_column_name,
                schema_name=schema_name,
                sql_query_filter=source_id_filter,
            )
            self._fetch_and_upsert_batches(
                ids_to_update,
                fetch_rows_fn,
                table_name,
                schema_name,
                batch_size,
                id_column_names=primary_key_columns,
            )

        if ids_to_add:
            self._fetch_and_upsert_batches(
                ids_to_add,
                fetch_rows_fn,
                table_name,
                schema_name,
                batch_size,
                id_column_names=primary_key_columns,
            )

    @abstractmethod
    def delete_rows_from_table(
        self,
        table_name: str,
        ids: list[str | int],
        schema_name: Optional[str] = None,
        id_column_name: str = CHUNK_ID_COLUMN,
        sql_query_filter: Optional[str] = None,
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
