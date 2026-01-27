"""add condition builder and parameter type to port definitions

Revision ID: d5e6f7a8b9c0
Revises: 9e46c1d3afb3
Create Date: 2026-01-26 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from ada_backend.database.utils import create_enum_if_not_exists

# revision identifiers, used by Alembic.
revision: str = "d5e6f7a8b9c0"
down_revision: Union[str, None] = "9e46c1d3afb3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add 'ConditionBuilder' value to the ui_component enum
    op.execute("ALTER TYPE ui_component ADD VALUE IF NOT EXISTS 'ConditionBuilder'")

    # Add parameter type to port definitions
    create_enum_if_not_exists(
        op.get_bind(),
        [
            "string",
            "integer",
            "float",
            "boolean",
            "json",
            "component",
            "tool",
            "data_source",
            "secrets",
            "llm_api_key",
            "llm_model",
        ],
        "parameter_type",
    )
    parameter_type_enum = postgresql.ENUM(
        "string",
        "integer",
        "float",
        "boolean",
        "json",
        "component",
        "tool",
        "data_source",
        "secrets",
        "llm_api_key",
        "llm_model",
        name="parameter_type",
        create_type=False,
    )
    op.add_column(
        "port_definitions",
        sa.Column(
            "parameter_type",
            parameter_type_enum,
            nullable=True,
        ),
    )


def downgrade() -> None:
    # PostgreSQL does not support removing enum values.
    # The 'ConditionBuilder' value will remain in the enum type even after downgrade.

    # Remove parameter type from port definitions
    op.drop_column("port_definitions", "parameter_type")
