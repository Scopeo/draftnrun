"""update api keys table

Revision ID: 8b393d7c2c4b
Revises: d4a5151de832
Create Date: 2025-09-04 18:01:58.754696

"""

# alembic revision: introduce polymorphic api_keys without legacy org table
from __future__ import annotations
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as psql


# revision identifiers, used by Alembic.
revision: str = "8b393d7c2c4b"
down_revision: Union[str, None] = "d4a5151de832"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    scope_enum = psql.ENUM("project", "organization", name="api_key_scope")
    scope_enum.create(conn, checkfirst=True)

    # 1) Add discriminator column to base api_keys
    op.add_column(
        "api_keys",
        sa.Column("type", scope_enum, nullable=False, server_default="project"),
    )

    # 2) Create child table for project keys
    op.create_table(
        "project_api_keys",
        sa.Column(
            "id",
            psql.UUID(as_uuid=True),
            sa.ForeignKey("api_keys.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "project_id",
            psql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_project_api_keys_project_id",
        "project_api_keys",
        ["project_id"],
        unique=False,
    )

    # 3) Move existing project_id links into child table
    conn.execute(
        sa.text(
            """
            INSERT INTO project_api_keys (id, project_id)
            SELECT id, project_id
            FROM api_keys
            WHERE project_id IS NOT NULL
            """
        )
    )

    # 4) Drop project_id from base table now that link is in child
    with op.batch_alter_table("api_keys") as batch:
        batch.drop_column("project_id")

    # 5) Create (empty) child table for org keys — no data migration
    op.create_table(
        "org_api_keys",
        sa.Column(
            "id",
            psql.UUID(as_uuid=True),
            sa.ForeignKey("api_keys.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "organization_id",
            psql.UUID(as_uuid=True),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_org_api_keys_organization_id",
        "org_api_keys",
        ["organization_id"],
        unique=False,
    )

    # 6) Remove server default on discriminator after backfill
    with op.batch_alter_table("api_keys") as batch:
        batch.alter_column("type", server_default=None)


def downgrade() -> None:
    conn = op.get_bind()

    # 1) Add project_id back to base (nullable for backfill)
    with op.batch_alter_table("api_keys") as batch:
        batch.add_column(sa.Column("project_id", psql.UUID(as_uuid=True), nullable=True))

    # 2) Restore project_id from child table
    conn.execute(
        sa.text(
            """
            UPDATE api_keys a
            SET project_id = p.project_id
            FROM project_api_keys p
            WHERE p.id = a.id
            """
        )
    )
    conn.execute(
        sa.text(
            """
        DELETE FROM api_keys
        WHERE "type"::text = 'organization'
           OR "type" = 'organization'
    """
        )
    )

    # 3) Make project_id NOT NULL again (match original schema)
    with op.batch_alter_table("api_keys") as batch:
        batch.alter_column("project_id", existing_type=psql.UUID(as_uuid=True), nullable=False)

    # 4) Drop child tables + their indexes
    op.drop_index("ix_project_api_keys_project_id", table_name="project_api_keys")
    op.drop_table("project_api_keys")

    op.drop_index("ix_org_api_keys_organization_id", table_name="org_api_keys")
    op.drop_table("org_api_keys")

    # 5) Drop discriminator column
    with op.batch_alter_table("api_keys") as batch:
        batch.drop_column("type")

    # 6) Drop enum type
    scope_enum = psql.ENUM("project", "organization", name="api_key_scope")
    scope_enum.drop(conn, checkfirst=True)
