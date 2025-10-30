import json

import snowflake.connector
from data_ingestion.utils import sanitize_filename

from settings import settings


def connect_to_snowflake(
    snowflake_account_identifier: str = settings.SNOWFLAKE_ACCOUNT,
    snowflake_user: str = settings.SNOWFLAKE_USER,
    snowflake_password: str = settings.SNOWFLAKE_PASSWORD,
):
    """
    Connect to Snowflake with timeout and connection retry limits.
    Raises ConnectionError if unable to connect.
    """
    if not all([snowflake_account_identifier, snowflake_user, snowflake_password]):
        raise ConnectionError(
            "Missing Snowflake credentials. Please ensure SNOWFLAKE_ACCOUNT, "
            "SNOWFLAKE_USER, and SNOWFLAKE_PASSWORD are set."
        )

    try:
        connector = snowflake.connector.connect(
            user=snowflake_user,
            password=snowflake_password,
            account=snowflake_account_identifier,
            client_session_keep_alive=True,
            login_timeout=5,
            network_timeout=5,
        )
        return connector
    except Exception as e:
        error_msg = (
            f"Failed to connect to Snowflake. "
            f"Account: {snowflake_account_identifier}, User: {snowflake_user}. "
            f"Error: {str(e)}"
        )
        raise ConnectionError(error_msg) from e


def escape_sql_string(val: str) -> str:
    """Escape single quotes in a string for SQL."""
    return val.replace("'", "\\'")


def dict_to_object_construct(d: dict) -> str:
    """Convert a dictionary into an OBJECT_CONSTRUCT SQL statement."""
    components = []
    for key, val in d.items():
        key = escape_sql_string(key)
        if isinstance(val, dict):
            # Recursive call for nested dictionaries
            val = dict_to_object_construct(val)
            components.append(f"'{key}', {val}")
        else:
            val = escape_sql_string(str(val))
            components.append(f"'{key}', '{val}'")
    return f"OBJECT_CONSTRUCT({', '.join(components)})"


def format_json(prettified_json: str) -> str:
    if prettified_json is None:
        return None
    data = json.loads(prettified_json)
    minified_json = json.dumps(data)

    return minified_json


def create_snowflake_database(
    database_name: str,
    snowflake_role: str,
    snowflake_warehouse: str,
):
    database_name = sanitize_filename(database_name)
    connector = connect_to_snowflake()
    connector.cursor().execute(f"USE ROLE {snowflake_role}")
    connector.cursor().execute(f"USE WAREHOUSE {snowflake_warehouse}")
    connector.cursor().execute(f'CREATE DATABASE IF NOT EXISTS "{database_name}"')
    return f'"{database_name}"'
