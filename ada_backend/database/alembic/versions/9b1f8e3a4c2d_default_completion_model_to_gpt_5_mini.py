"""Default completion model to GPT-5 Mini.

Revision ID: 9b1f8e3a4c2d
Revises: 2f23d1a93b76
Create Date: 2026-06-02
"""

from typing import Sequence, Union

from alembic import op

revision: str = "9b1f8e3a4c2d"
down_revision: Union[str, None] = "2f23d1a93b76"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

deploy_strategy = "migrate-first"

PARAM_NAME = "completion_model"
OLD_MODEL = "anthropic:claude-haiku-4-5"
NEW_MODEL = "openai:gpt-5-mini"


def upgrade() -> None:
    op.execute(f"""
        UPDATE component_parameter_definitions
        SET "default" = '{NEW_MODEL}'
        WHERE name = '{PARAM_NAME}'
          AND "default" = '{OLD_MODEL}'
    """)


def downgrade() -> None:
    op.execute(f"""
        UPDATE component_parameter_definitions
        SET "default" = '{OLD_MODEL}'
        WHERE name = '{PARAM_NAME}'
          AND "default" = '{NEW_MODEL}'
    """)
