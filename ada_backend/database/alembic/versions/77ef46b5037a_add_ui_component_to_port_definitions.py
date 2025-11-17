"""add ui_component to port_definitions

Revision ID: 77ef46b5037a
Revises: a4576629806f
Create Date: 2025-01-27 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from ada_backend.database.utils import create_enum_if_not_exists

# revision identifiers, used by Alembic.
revision: str = "77ef46b5037a"
down_revision: Union[str, None] = "a4576629806f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Ensure ui_component enum exists (it should already exist from ComponentParameterDefinition)
    create_enum_if_not_exists(
        connection=op.get_bind(),
        enum_values=[
            "Autocomplete",
            "Checkbox",
            "Combobox",
            "Date Time Picker",
            "Editors",
            "File Input",
            "Radio",
            "Custom Input",
            "Range Slider",
            "Rating",
            "Select",
            "Slider",
            "Switch",
            "Textarea",
            "Textfield",
            "FileUpload",
            "JSON Builder",
        ],
        enum_name="ui_component",
    )

    ui_component_enum = postgresql.ENUM(
        "Autocomplete",
        "Checkbox",
        "Combobox",
        "Date Time Picker",
        "Editors",
        "File Input",
        "Radio",
        "Custom Input",
        "Range Slider",
        "Rating",
        "Select",
        "Slider",
        "Switch",
        "Textarea",
        "Textfield",
        "FileUpload",
        "JSON Builder",
        name="ui_component",
        create_type=False,
    )

    op.add_column(
        "port_definitions",
        sa.Column("ui_component", ui_component_enum, nullable=True),
    )
    op.add_column(
        "port_definitions",
        sa.Column("ui_component_properties", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "port_definitions",
        sa.Column("is_optional", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("port_definitions", "is_optional")
    op.drop_column("port_definitions", "ui_component_properties")
    op.drop_column("port_definitions", "ui_component")
