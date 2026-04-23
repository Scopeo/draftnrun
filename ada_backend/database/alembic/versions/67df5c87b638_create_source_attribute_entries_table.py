"""create source attribute entries table

Revision ID: 67df5c87b638
Revises: j1k2l3m4n5o6
Create Date: 2026-04-23 12:59:35.649247

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "67df5c87b638"
down_revision: Union[str, None] = "j1k2l3m4n5o6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

deploy_strategy: Union[str, None] = "migrate-first"


def upgrade() -> None:
    op.create_table(
        "source_attribute_entries",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("source_id", sa.UUID(), nullable=False),
        sa.Column("attribute_name", sa.String(), nullable=False),
        sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["source_id"], ["data_sources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_id",
            "attribute_name",
            name="uq_source_attribute_entries_source_id_attribute_name",
        ),
    )
    op.create_index(
        "ix_source_attribute_entries_source_id",
        "source_attribute_entries",
        ["source_id"],
        unique=False,
    )

    op.execute(
        sa.text(
            """
            INSERT INTO source_attribute_entries (id, source_id, attribute_name, value, created_at, updated_at)
            SELECT
                gen_random_uuid(),
                source_id,
                attr_name,
                attr_value,
                created_at,
                updated_at
            FROM source_attributes,
            LATERAL (
                VALUES
                    ('access_token', to_jsonb(access_token)),
                    ('path', to_jsonb(path)),
                    ('folder_id', to_jsonb(folder_id)),
                    ('source_db_url', to_jsonb(source_db_url::text)),
                    ('source_table_name', to_jsonb(source_table_name)),
                    ('id_column_name', to_jsonb(id_column_name)),
                    ('source_schema_name', to_jsonb(source_schema_name)),
                    ('chunk_size', to_jsonb(chunk_size)),
                    ('chunk_overlap', to_jsonb(chunk_overlap)),
                    ('timestamp_column_name', to_jsonb(timestamp_column_name)),
                    ('url_pattern', to_jsonb(url_pattern)),
                    ('update_existing', to_jsonb(update_existing)),
                    ('query_filter', to_jsonb(query_filter)),
                    ('timestamp_filter', to_jsonb(timestamp_filter)),
                    ('list_of_files_from_local_folder', NULLIF(list_of_files_from_local_folder::jsonb, 'null'::jsonb)),
                    ('text_column_names', NULLIF(text_column_names::jsonb, 'null'::jsonb)),
                    ('metadata_column_names', NULLIF(metadata_column_names::jsonb, 'null'::jsonb))
            ) AS attribute_values(attr_name, attr_value)
            WHERE attr_value IS NOT NULL
            """
        )
    )


def downgrade() -> None:
    op.drop_index("ix_source_attribute_entries_source_id", table_name="source_attribute_entries")
    op.drop_table("source_attribute_entries")
