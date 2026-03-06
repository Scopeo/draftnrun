"""add encrypted values to org variable sets

Revision ID: b1c2d3e4f5a6
Revises: hc4u6epu6y03
Create Date: 2026-03-06 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from cryptography.fernet import Fernet
from sqlalchemy.dialects import postgresql

from settings import settings

# revision identifiers, used by Alembic.
revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, None] = "hc4u6epu6y03"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "org_variable_sets",
        sa.Column(
            "encrypted_values",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )

    bind = op.get_bind()
    cipher = Fernet(settings.FERNET_KEY)

    secret_names_by_org: dict[str, set[str]] = {}
    secret_rows = bind.execute(
        sa.text(
            """
            SELECT organization_id::text AS organization_id, name
            FROM org_variable_definitions
            WHERE type = 'secret'
            """
        )
    ).fetchall()
    for row in secret_rows:
        secret_names_by_org.setdefault(row.organization_id, set()).add(row.name)

    set_rows = bind.execute(
        sa.text(
            """
            SELECT id, organization_id::text AS organization_id, values, encrypted_values
            FROM org_variable_sets
            """
        )
    ).fetchall()

    for row in set_rows:
        secret_names = secret_names_by_org.get(row.organization_id, set())
        if not secret_names:
            continue

        values = dict(row.values or {})
        encrypted_values = dict(row.encrypted_values or {})
        migrated = False

        for key in list(values.keys()):
            if key not in secret_names:
                continue
            raw_value = values.pop(key)
            if raw_value is None:
                migrated = True
                continue
            encrypted_values[key] = cipher.encrypt(str(raw_value).encode()).decode()
            migrated = True

        if not migrated:
            continue

        bind.execute(
            sa.text(
                """
                UPDATE org_variable_sets
                SET values = :values,
                    encrypted_values = :encrypted_values
                WHERE id = :set_id
                """
            ),
            {
                "set_id": row.id,
                "values": values,
                "encrypted_values": encrypted_values,
            },
        )

    op.alter_column("org_variable_sets", "encrypted_values", server_default=None)


def downgrade() -> None:
    bind = op.get_bind()
    cipher = Fernet(settings.FERNET_KEY)

    secret_names_by_org: dict[str, set[str]] = {}
    secret_rows = bind.execute(
        sa.text(
            """
            SELECT organization_id::text AS organization_id, name
            FROM org_variable_definitions
            WHERE type = 'secret'
            """
        )
    ).fetchall()
    for row in secret_rows:
        secret_names_by_org.setdefault(row.organization_id, set()).add(row.name)

    set_rows = bind.execute(
        sa.text(
            """
            SELECT id, organization_id::text AS organization_id, values, encrypted_values
            FROM org_variable_sets
            """
        )
    ).fetchall()

    for row in set_rows:
        secret_names = secret_names_by_org.get(row.organization_id, set())
        if not secret_names:
            continue

        values = dict(row.values or {})
        encrypted_values = dict(row.encrypted_values or {})
        migrated = False

        for key in secret_names:
            encrypted_value = encrypted_values.pop(key, None)
            if not encrypted_value:
                continue
            values[key] = cipher.decrypt(encrypted_value.encode()).decode()
            migrated = True

        if not migrated:
            continue

        bind.execute(
            sa.text(
                """
                UPDATE org_variable_sets
                SET values = :values
                WHERE id = :set_id
                """
            ),
            {
                "set_id": row.id,
                "values": values,
            },
        )

    op.drop_column("org_variable_sets", "encrypted_values")
