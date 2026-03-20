import logging
from typing import Iterable, Optional

from pydantic import BaseModel, field_validator
from sqlalchemy import create_engine, text
from sqlalchemy.engine.url import make_url

PROCESSED_DATETIME_FIELD = "_processed_datetime"
CHUNK_ID_COLUMN = "chunk_id"
CREATED_AT_COLUMN = "created_at"
UPDATED_AT_COLUMN = "updated_at"

LOGGER = logging.getLogger(__name__)

PYTHON_TYPE_CAST: dict[str, type] = {
    "STRING": str,
    "VARCHAR": str,
    "TEXT": str,
    "INTEGER": int,
    "FLOAT": float,
    "BOOLEAN": bool,
    "UUID": str,
}


class DBColumn(BaseModel):
    name: str
    type: str
    is_primary: bool = False
    default: Optional[str] = None
    is_nullable: bool = True


class DBDefinition(BaseModel):
    columns: list[DBColumn]

    @field_validator("columns")
    def check_column_presence(cls, columns):
        column_names = [column.name for column in columns]
        if PROCESSED_DATETIME_FIELD not in column_names:
            LOGGER.warning(f"Missing column: {PROCESSED_DATETIME_FIELD}")
            for col in columns:
                if not col.name.islower():
                    LOGGER.warning(f"Column names should be lowercase for table definition: check {col.name}")
                matching_name = col.name == PROCESSED_DATETIME_FIELD
                matching_type = col.type == "DATETIME"
                matching_default = col.default == "CURRENT_TIMESTAMP"
                if matching_name and (not matching_type or not matching_default):
                    LOGGER.warning(
                        f"Column {PROCESSED_DATETIME_FIELD} should be of type DATETIME with default CURRENT_TIMESTAMP",
                    )
        return columns


def create_db_if_not_exists(target_db_url: str, admin_db_name: str = "postgres") -> None:
    """
    Create the target database if it does not exist.
    This function connects to the admin database (default: 'postgres') using the same credentials,
    host, and port as in the target_db_url. If the target database is missing, it will be created.
    Args:
        target_db_url (str): The SQLAlchemy database URL for the database you want to ensure exists.
        admin_db_name (str): The administrative database to connect to (defaults to 'postgres').
    """
    # Parse the target database URL and replace the database part with admin_db_name
    url_obj = make_url(target_db_url)
    admin_url_obj = url_obj.set(database=admin_db_name)

    # Create a SQLAlchemy engine for the admin database
    admin_engine = create_engine(admin_url_obj, isolation_level="AUTOCOMMIT")

    target_db_name = url_obj.database

    with admin_engine.connect() as conn:
        result = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname=:dbname"),
            {"dbname": target_db_name},
        )
        exists = result.scalar()
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{target_db_name}"'))
            print(f"Database '{target_db_name}' created.")
        else:
            print(f"Database '{target_db_name}' already exists.")


def cast_id_value(value, column_name: str, db_definition: DBDefinition):
    """Cast *value* to the Python type that matches the DB column definition."""
    column_type = next((col.type for col in db_definition.columns if col.name == column_name), None)
    if column_type is not None:
        py_type = PYTHON_TYPE_CAST.get(column_type)
        if py_type is not None and value is not None:
            return py_type(value)
    return value


def check_columns_matching_between_data_and_database_table(
    columns_data: Iterable[str],
    table_description: list[dict],
) -> None:
    AUTO_MANAGED_COLUMNS = {PROCESSED_DATETIME_FIELD, CREATED_AT_COLUMN, UPDATED_AT_COLUMN}

    column_table = {column["name"].lower() for column in table_description} - AUTO_MANAGED_COLUMNS
    data_cols = set(columns_data) - AUTO_MANAGED_COLUMNS
    if data_cols != column_table:
        LOGGER.error(f"Columns in data and table do not match : data {data_cols}, table {column_table}")
        raise ValueError("Columns in data and table do not match")
