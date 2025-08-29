"""add attributes to data sources

Revision ID: 6d40e78ae131
Revises: 0d0db05d4dac
Create Date: 2025-08-28 18:33:42.858056
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "6d40e78ae131"
down_revision: Union[str, None] = "0d0db05d4dac"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

FK_NAME = "fk_organization_secrets_data_source_id"


def upgrade() -> None:
    # columns
    op.add_column("data_sources", sa.Column("attributes", sa.JSON(), nullable=True))
    op.add_column("organization_secrets", sa.Column("data_source_id", sa.UUID(), nullable=True))

    # named FK (deterministic)
    op.create_foreign_key(
        FK_NAME,
        "organization_secrets",
        "data_sources",
        ["data_source_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # idempotent enum add
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_type t
                JOIN pg_enum e ON e.enumtypid = t.oid
                WHERE t.typname = 'org_secret_type'
                  AND e.enumlabel = 'database_url'
            ) THEN
                ALTER TYPE org_secret_type ADD VALUE 'database_url';
            END IF;
        EXCEPTION
            WHEN duplicate_object THEN
                NULL;
        END$$;
        """
    )


def downgrade() -> None:
    # drop FK first
    op.drop_constraint(FK_NAME, "organization_secrets", type_="foreignkey")

    # drop columns
    op.drop_column("organization_secrets", "data_source_id")
    op.drop_column("data_sources", "attributes")

    # if you had a default on secret_type, drop it before type change to avoid issues
    # (safe even if no default existed)
    op.execute("ALTER TABLE organization_secrets ALTER COLUMN secret_type DROP DEFAULT")

    # IMPORTANT: remap rows that use the soon-to-be-removed value
    # choose the fallback that fits your app (here: 'password')
    op.execute(
        """
        UPDATE organization_secrets
        SET secret_type = 'password'
        WHERE secret_type = 'database_url';
        """
    )

    # recreate enum without 'database_url'
    op.execute("ALTER TYPE org_secret_type RENAME TO org_secret_type_old")
    op.execute("CREATE TYPE org_secret_type AS ENUM ('llm_api_key', 'password')")
    op.execute(
        """
        ALTER TABLE organization_secrets
        ALTER COLUMN secret_type
        TYPE org_secret_type
        USING secret_type::text::org_secret_type
        """
    )
    op.execute("DROP TYPE org_secret_type_old")
