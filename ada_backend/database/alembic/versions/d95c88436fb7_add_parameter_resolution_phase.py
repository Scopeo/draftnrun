"""add_parameter_resolution_phase

Revision ID: d95c88436fb7
Revises: 8cc2f22a492e
Create Date: 2025-10-13 16:54:35.142289

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'd95c88436fb7'
down_revision: Union[str, None] = 'd0d10b5a7983'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create enum type
    parameter_resolution_phase_enum = postgresql.ENUM(
        'constructor',
        'runtime',
        name='parameter_resolution_phase',
        create_type=True
    )
    parameter_resolution_phase_enum.create(op.get_bind())

    # Add column with default value
    op.add_column(
        'basic_parameters',
        sa.Column(
            'resolution_phase',
            sa.Enum('constructor', 'runtime', name='parameter_resolution_phase'),
            nullable=False,
            server_default='constructor'
        )
    )

    # Populate existing rows based on current heuristic:
    # If parameter name matches an input port name, it's runtime; otherwise constructor
    op.execute("""
        UPDATE basic_parameters bp
        SET resolution_phase = CASE
            WHEN EXISTS (
                SELECT 1
                FROM port_definitions pd
                WHERE pd.component_id = (
                    SELECT ci.component_id
                    FROM component_instances ci
                    WHERE ci.id = bp.component_instance_id
                )
                AND pd.port_type = 'INPUT'
                AND pd.name = (
                    SELECT cpd.name
                    FROM component_parameter_definitions cpd
                    WHERE cpd.id = bp.parameter_definition_id
                )
            ) THEN 'runtime'::parameter_resolution_phase
            ELSE 'constructor'::parameter_resolution_phase
        END
    """)


def downgrade() -> None:
    # Remove column
    op.drop_column('basic_parameters', 'resolution_phase')

    # Drop enum type
    parameter_resolution_phase_enum = postgresql.ENUM(
        'constructor',
        'runtime',
        name='parameter_resolution_phase'
    )
    parameter_resolution_phase_enum.drop(op.get_bind())
