"""migration cerebras deprecated model(Qwen 3 235B)

Revision ID: 3253550650e4
Revises: ed8f19491923
Create Date: 2025-09-17 12:07:37.418279

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "3253550650e4"
down_revision: Union[str, None] = "ed8f19491923"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OLD = "cerebras:qwen-3-235b-a22b"
NEW = "cerebras:qwen-3-235b-a22b-instruct-2507"
PARAM_NAME = "completion_model"


def upgrade() -> None:
    conn = op.get_bind()
    conn.exec_driver_sql(
        """
        UPDATE basic_parameters bp
        SET value = %(new)s
        WHERE bp.value = %(old)s
          AND bp.parameter_definition_id IN (
              SELECT cpd.id
              FROM component_parameter_definitions cpd
              WHERE cpd.name = %(param_name)s
          )
        """,
        {"old": OLD, "new": NEW, "param_name": PARAM_NAME},
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.exec_driver_sql(
        """
        UPDATE basic_parameters bp
        SET value = %(old)s
        WHERE bp.value = %(new)s
          AND bp.parameter_definition_id IN (
              SELECT cpd.id
              FROM component_parameter_definitions cpd
              WHERE cpd.name = %(param_name)s
          )
        """,
        {"old": OLD, "new": NEW, "param_name": PARAM_NAME},
    )
