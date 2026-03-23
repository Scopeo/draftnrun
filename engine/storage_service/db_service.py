import logging
from abc import ABC, abstractmethod
from typing import Iterator, Optional

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
        batch_size: Optional[int] = None,
        schema_name: Optional[str] = None,
        sql_query_filter: Optional[str] = None,
    ) -> Iterator[list[dict]]:
        """Yield batches of rows as list[dict]."""
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
        import pandas as pd

        rows = self._fetch_sql_query_as_dicts(query)
        return pd.DataFrame(rows)

    def update_table(
        self,
        new_rows: list[dict],
        table_name: str,
        table_definition: DBDefinition,
        id_column_name: str,
        schema_name: Optional[str] = None,
        timestamp_column_name: Optional[str] = None,
        append_mode: bool = True,
        sql_query_filter: Optional[str] = None,
        source_id: Optional[str] = None,
    ) -> None:
        """
        Update a table on Database with new rows (list[dict]).
        If the table does not exist, it will be created.
        """
        if not new_rows:
            LOGGER.info("Empty row list provided, skipping update")
            return

        target_table_name = f"{schema_name}.{table_name}" if schema_name else table_name
        table_exists = self.table_exists(table_name, schema_name=schema_name)

        if not table_exists:
            LOGGER.info(f"Table {target_table_name} does not exist. Creating it...")
            self.create_table(
                table_name=table_name,
                table_definition=table_definition,
                schema_name=schema_name,
            )
            self.insert_rows(rows=new_rows, table_name=table_name, schema_name=schema_name)
        else:
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

            existing_rows_by_id: dict = {}
            for row in existing_rows:
                row_id = cast_id_value(row[id_column_name], id_column_name, table_definition)
                existing_rows_by_id[row_id] = row

            incoming_rows_by_id: dict = {}
            for row in new_rows:
                row_id = cast_id_value(row[id_column_name], id_column_name, table_definition)
                incoming_rows_by_id[row_id] = row

            common_ids = set(incoming_rows_by_id.keys()) & set(existing_rows_by_id.keys())

            if timestamp_column_name and not sql_query_filter:
                ids_to_update = set()
                for shared_id in common_ids:
                    incoming_dt = parse_datetime(incoming_rows_by_id[shared_id].get(timestamp_column_name))
                    existing_dt = parse_datetime(existing_rows_by_id[shared_id].get(timestamp_column_name))
                    if incoming_dt is not None and existing_dt is not None:
                        if make_naive_utc(incoming_dt) > make_naive_utc(existing_dt):
                            ids_to_update.add(shared_id)
                    elif incoming_rows_by_id[shared_id] != existing_rows_by_id[shared_id]:
                        ids_to_update.add(shared_id)
            else:
                ids_to_update = common_ids

            LOGGER.info(f"Found {len(ids_to_update)} rows to update in the table")
            rows_to_update = [incoming_rows_by_id[row_id] for row_id in ids_to_update]

            if rows_to_update:
                self._refresh_table_from_rows(
                    rows=rows_to_update,
                    table_name=table_name,
                    id_column=id_column_name,
                    table_definition=table_definition,
                    schema_name=schema_name,
                )
            else:
                LOGGER.info("No rows to update, skipping update operation")

            existing_count = sum(
                1
                for row in new_rows
                if cast_id_value(row[id_column_name], id_column_name, table_definition) in all_existing_ids
            )
            LOGGER.info(f"Found {existing_count} existing rows in the table")
            rows_to_insert = [
                row
                for row in new_rows
                if cast_id_value(row[id_column_name], id_column_name, table_definition) not in all_existing_ids
            ]
            self.insert_rows(rows_to_insert, table_name, schema_name=schema_name)

            if not append_mode:
                filtered_existing_ids = set(existing_rows_by_id.keys())
                incoming_ids_in_scope = set(incoming_rows_by_id.keys())
                ids_to_delete = filtered_existing_ids - incoming_ids_in_scope

                LOGGER.info(f"Found {len(ids_to_delete)} rows to delete in the filtered scope")
                if ids_to_delete:
                    self.delete_rows_from_table(
                        table_name=table_name,
                        ids=list(ids_to_delete),
                        id_column_name=id_column_name,
                        schema_name=schema_name,
                    )

    @abstractmethod
    def _refresh_table_from_rows(
        self,
        rows: list[dict],
        table_name: str,
        id_column: str,
        table_definition: DBDefinition,
        schema_name: Optional[str] = None,
    ) -> None:
        pass

    def _refresh_table_from_df(
        self,
        df,
        table_name: str,
        id_column: str,
        table_definition: DBDefinition,
        schema_name: Optional[str] = None,
    ) -> None:
        """Convenience method that accepts a pandas DataFrame. Prefer _refresh_table_from_rows."""
        rows = df.to_dict(orient="records") if hasattr(df, "to_dict") else list(df)
        self._refresh_table_from_rows(rows, table_name, id_column, table_definition, schema_name)

    def delete_stale_rows(
        self,
        table_name: str,
        id_column_name: str,
        incoming_ids: set,
        table_definition: DBDefinition,
        schema_name: Optional[str] = None,
        sql_query_filter: Optional[str] = None,
        source_id: Optional[str] = None,
    ) -> None:
        """Delete rows in the scoped table whose IDs are not in incoming_ids."""
        target_table_name = f"{schema_name}.{table_name}" if schema_name else table_name
        query = f"SELECT {id_column_name} FROM {target_table_name}"
        filters = []
        if source_id is not None:
            filters.append(f"source_id = '{source_id}'")
        if sql_query_filter:
            filters.append(f"({sql_query_filter})")
        final_query = f"{query} WHERE {' AND '.join(filters)};" if filters else f"{query};"
        existing_rows = self._fetch_sql_query_as_dicts(final_query)
        existing_ids = {cast_id_value(row[id_column_name], id_column_name, table_definition) for row in existing_rows}
        cast_incoming_ids = {cast_id_value(id_, id_column_name, table_definition) for id_ in incoming_ids}
        ids_to_delete = existing_ids - cast_incoming_ids
        LOGGER.info(f"Found {len(ids_to_delete)} stale rows to delete in the filtered scope")
        if ids_to_delete:
            self.delete_rows_from_table(
                table_name=table_name,
                ids=list(ids_to_delete),
                id_column_name=id_column_name,
                schema_name=schema_name,
            )

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
