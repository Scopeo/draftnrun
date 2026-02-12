import logging
import re

import sqlalchemy as sa

from engine.components.types import ToolDescription

LOGGER = logging.getLogger(__name__)

DEFAULT_TOOL_DESCRIPTION = ToolDescription(
    name="default",
    description="",
    tool_properties={},
    required_tool_properties=[],
)


def update_model_fields(current_state, new_state):
    protected_fields = ["_sa_instance_state", "parameter_group_id", "parameter_order_within_group"]

    for key, value in current_state.__dict__.items():
        if key in protected_fields:
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


def create_enum_if_not_exists(
    connection,
    enum_values,
    enum_name,
    schema="public",
):
    """
    Create a PostgreSQL enum type if it doesn't exist in the given schema.
    """
    # escape enum values
    escaped_values = [v.replace("'", "''") for v in enum_values]
    values_sql = ", ".join(f"'{v}'" for v in escaped_values)

    sql = f"""
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1
            FROM pg_type t
            JOIN pg_namespace n ON n.oid = t.typnamespace
            WHERE t.typname = '{enum_name}'
              AND n.nspname = '{schema}'
        ) THEN
            CREATE TYPE {schema}.{enum_name} AS ENUM ({values_sql});
        END IF;
    END
    $$;
    """
    connection.execute(sa.text(sql))


def drop_enum_if_exists(
    connection,
    enum_name,
    schema="public",
):
    """
    Drop a PostgreSQL enum type if it exists in the given schema.
    """
    sql = f"""
    DO $$
    BEGIN
        IF EXISTS (
            SELECT 1
            FROM pg_type t
            JOIN pg_namespace n ON n.oid = t.typnamespace
            WHERE t.typname = '{enum_name}'
              AND n.nspname = '{schema}'
        ) THEN
            DROP TYPE {schema}.{enum_name} CASCADE;
        END IF;
    END
    $$;
    """
    connection.execute(sa.text(sql))


def camel_to_snake(name: str) -> str:
    """Convert CamelCase or lowerCamelCase to snake_case."""
    s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1).lower()
