"""Add widget schema and tables

Revision ID: e18942767d31
Revises: 3519709bead8
Create Date: 2025-12-05 09:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


# revision identifiers, used by Alembic.
revision: str = "e18942767d31"
down_revision: Union[str, None] = "3519709bead8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create the widget schema
    op.execute("CREATE SCHEMA IF NOT EXISTS widget")

    # Create widgets table in widget schema
    op.create_table(
        "widgets",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("widget_key", sa.String(64), nullable=False),
        sa.Column("project_id", UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "config",
            JSONB,
            nullable=False,
            server_default=sa.text(
                """'{
                    "theme": {
                        "primary_color": "#6366F1",
                        "secondary_color": "#4F46E5",
                        "background_color": "#FFFFFF",
                        "text_color": "#1F2937",
                        "border_radius": 12,
                        "font_family": "Inter, system-ui, sans-serif",
                        "logo_url": null
                    },
                    "first_messages": [],
                    "suggestions": [],
                    "placeholder_text": "Type a message...",
                    "powered_by_visible": true
                }'::jsonb"""
            ),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["project_id"], ["public.projects.id"], ondelete="CASCADE"),
        schema="widget",
    )
    # Note: Primary key "id" is automatically indexed, no need for explicit index
    op.create_index(
        op.f("ix_widget_widgets_widget_key"),
        "widgets",
        ["widget_key"],
        unique=True,
        schema="widget",
    )
    op.create_index(
        op.f("ix_widget_widgets_organization_id"),
        "widgets",
        ["organization_id"],
        unique=False,
        schema="widget",
    )
    op.create_index(
        op.f("ix_widget_widgets_project_id"),
        "widgets",
        ["project_id"],
        unique=False,
        schema="widget",
    )


def downgrade() -> None:
    # Drop widgets table indexes
    op.drop_index(
        op.f("ix_widget_widgets_project_id"),
        table_name="widgets",
        schema="widget",
    )
    op.drop_index(
        op.f("ix_widget_widgets_organization_id"),
        table_name="widgets",
        schema="widget",
    )
    op.drop_index(
        op.f("ix_widget_widgets_widget_key"),
        table_name="widgets",
        schema="widget",
    )
    op.drop_table("widgets", schema="widget")

    # Drop the widget schema
    op.execute("DROP SCHEMA IF EXISTS widget")
