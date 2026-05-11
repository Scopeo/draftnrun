"""Backfill port_definition_id on input_port_instances where it is NULL.

Joins through component_instances → port_definitions to resolve the
catalogue port definition for each named input port.

Revision ID: b4c5d6e7f8b0
Revises: a3b4c5d6e7f9
Create Date: 2026-05-06
"""

from typing import Sequence, Union

from alembic import op

revision: str = "b4c5d6e7f8b0"
down_revision: Union[str, None] = "a3b4c5d6e7f9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

deploy_strategy = "migrate-first"


def upgrade() -> None:
    op.execute("""
        UPDATE port_instances pi
        SET port_definition_id = pd.id
        FROM input_port_instances ipi,
             component_instances ci,
             port_definitions pd
        WHERE ipi.id = pi.id
          AND ci.id = pi.component_instance_id
          AND pd.component_version_id = ci.component_version_id
          AND pd.name = pi.name
          AND pd.port_type = 'INPUT'
          AND pi.port_definition_id IS NULL
    """)


def downgrade() -> None:
    pass
