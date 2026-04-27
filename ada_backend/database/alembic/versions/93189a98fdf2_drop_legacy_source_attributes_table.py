"""drop legacy source_attributes table

Revision ID: 93189a98fdf2
Revises: k2l3m4n5o6p7
Create Date: 2026-04-27 14:12:47.867361

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "93189a98fdf2"
down_revision: Union[str, None] = "k2l3m4n5o6p7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

deploy_strategy: Union[str, None] = "code-first"


def upgrade() -> None:
    op.drop_index(op.f("ix_source_attributes_id"), table_name="source_attributes")
    op.drop_table("source_attributes")


def downgrade() -> None:
    op.create_table(
        "source_attributes",
        sa.Column("id", sa.UUID(), autoincrement=False, nullable=False),
        sa.Column("source_id", sa.UUID(), autoincrement=False, nullable=False),
        sa.Column("access_token", sa.VARCHAR(), autoincrement=False, nullable=True),
        sa.Column("path", sa.VARCHAR(), autoincrement=False, nullable=True),
        sa.Column(
            "list_of_files_from_local_folder",
            postgresql.JSON(astext_type=sa.Text()),
            autoincrement=False,
            nullable=True,
        ),
        sa.Column("folder_id", sa.VARCHAR(), autoincrement=False, nullable=True),
        sa.Column("source_db_url", sa.UUID(), autoincrement=False, nullable=True),
        sa.Column("source_table_name", sa.VARCHAR(), autoincrement=False, nullable=True),
        sa.Column("id_column_name", sa.VARCHAR(), autoincrement=False, nullable=True),
        sa.Column("text_column_names", postgresql.JSON(astext_type=sa.Text()), autoincrement=False, nullable=True),
        sa.Column("source_schema_name", sa.VARCHAR(), autoincrement=False, nullable=True),
        sa.Column("chunk_size", sa.INTEGER(), autoincrement=False, nullable=True),
        sa.Column("chunk_overlap", sa.INTEGER(), autoincrement=False, nullable=True),
        sa.Column("metadata_column_names", postgresql.JSON(astext_type=sa.Text()), autoincrement=False, nullable=True),
        sa.Column("timestamp_column_name", sa.VARCHAR(), autoincrement=False, nullable=True),
        sa.Column("url_pattern", sa.VARCHAR(), autoincrement=False, nullable=True),
        sa.Column("update_existing", sa.BOOLEAN(), autoincrement=False, nullable=False),
        sa.Column("query_filter", sa.VARCHAR(), autoincrement=False, nullable=True),
        sa.Column("timestamp_filter", sa.VARCHAR(), autoincrement=False, nullable=True),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            autoincrement=False,
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            autoincrement=False,
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["source_db_url"],
            ["organization_secrets.id"],
            name=op.f("source_attributes_source_db_url_fkey"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["data_sources.id"],
            name=op.f("source_attributes_source_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("source_attributes_pkey")),
    )
    op.create_index(op.f("ix_source_attributes_id"), "source_attributes", ["id"], unique=False)
