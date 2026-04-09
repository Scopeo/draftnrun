"""remove document smart-rag catalog entries

Revision ID: b6c7d8e9f0a1
Revises: a1b2c3d4e5f9
Create Date: 2026-04-09
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b6c7d8e9f0a1"
down_revision: Union[str, None] = "a1b2c3d4e5f9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

deploy_strategy: Union[str, None] = "code-first"

DOCUMENT_ENHANCED_TOOL_DESCRIPTION_ID = "d01978d9-c785-4492-9e71-7af0aa8c05f7"

DOCUMENT_SEARCH_COMPONENT_ID = "79399392-25ba-4cea-9f25-2738765dc329"
DOCUMENT_ENHANCED_COMPONENT_ID = "6460b304-640c-4468-abd3-67bbff6902d4"
DOCUMENT_REACT_LOADER_COMPONENT_ID = "1c2fdf5b-4a8d-4788-acb6-86b00124c7ce"


def upgrade() -> None:
    bind = op.get_bind()

    bind.execute(
        sa.text(
            """
            DELETE FROM tool_descriptions
            WHERE id = CAST(:tool_description_id AS uuid)
            """,
        ),
        {"tool_description_id": DOCUMENT_ENHANCED_TOOL_DESCRIPTION_ID},
    )
    bind.execute(
        sa.text(
            f"""
            DELETE FROM components
            WHERE id IN (
                '{DOCUMENT_SEARCH_COMPONENT_ID}'::uuid,
                '{DOCUMENT_ENHANCED_COMPONENT_ID}'::uuid,
                '{DOCUMENT_REACT_LOADER_COMPONENT_ID}'::uuid
            )
            """,
        ),
    )


def downgrade() -> None:
    pass
