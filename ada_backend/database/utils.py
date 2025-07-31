import logging
import re

import sqlalchemy as sa

from engine.agent.types import ToolDescription
from settings import settings

LOGGER = logging.getLogger(__name__)

DEFAULT_TOOL_DESCRIPTION = ToolDescription(
    name="default",
    description="",
    tool_properties={},
    required_tool_properties=[],
)


def update_model_fields(current_state, new_state):
    for key, value in current_state.__dict__.items():
        if key in ["_sa_instance_state"]:
            continue

        if key not in new_state.__dict__:
            setattr(new_state, key, value)
        else:
            if getattr(new_state, key) != value:
                setattr(current_state, key, getattr(new_state, key))
                LOGGER.info(f"Updated {key} to {getattr(new_state, key)}")


def models_are_equal(current_state, new_state):
    for key in current_state.__dict__:
        if key in ["_sa_instance_state"]:
            continue
        if key not in new_state.__dict__:
            setattr(new_state, key, getattr(current_state, key))
        if getattr(current_state, key) != getattr(new_state, key):
            return False
    return True


def create_enum_if_not_exists(connection, enum_values, enum_name):
    """
    Helper function to create a PostgreSQL enum type if it doesn't exist.
    This function can be used in migration scripts.

    Args:
        connection: SQLAlchemy connection
        enum_values: List of string values for the enum
        enum_name: Name of the enum type in PostgreSQL (should be lowercase)
    """
    # Only create enums for PostgreSQL
    if settings.ADA_DB_DRIVER != "postgresql":
        return

    values_sql = ", ".join(f"'{value}'" for value in enum_values)

    sql = f"""
    DO $$
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = '{enum_name}') THEN
            CREATE TYPE {enum_name} AS ENUM ({values_sql});
        END IF;
    END
    $$;
    """

    connection.execute(sa.text(sql))


def camel_to_snake(name: str) -> str:
    """Convert CamelCase or lowerCamelCase to snake_case."""
    s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1).lower()
