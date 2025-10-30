"""use conversation history in qa

Revision ID: c79f503f855e
Revises: a86270305bab
Create Date: 2025-10-30 16:00:44.272757

"""

from typing import Sequence, Union
import json

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = "c79f503f855e"
down_revision: Union[str, None] = "a86270305bab"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Step 1: Add a temporary JSONB column
    op.add_column(
        "input_groundtruth",
        sa.Column("input_jsonb", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        schema="quality_assurance",
    )

    # Step 2: Migrate data - convert string input to JSON format with messages array
    connection = op.get_bind()
    result = connection.execute(
        text(
            """
        SELECT id, input
        FROM quality_assurance.input_groundtruth
        WHERE input IS NOT NULL
    """
        )
    )

    for row in result:
        record_id = row.id
        old_input = row.input

        # Convert string input to JSON format
        # If already JSON string, parse it
        # Otherwise wrap it in messages array
        try:
            # Try to parse as JSON first
            if isinstance(old_input, str):
                parsed = json.loads(old_input)
                # If it's already in the correct format, use it
                if isinstance(parsed, dict) and "messages" in parsed:
                    new_input = parsed
                else:
                    # Wrap old string/object in messages array
                    new_input = {"messages": [{"role": "user", "content": str(old_input)}]}
            else:
                # It's already a dict
                if isinstance(old_input, dict) and "messages" in old_input:
                    new_input = old_input
                else:
                    new_input = {"messages": [{"role": "user", "content": str(old_input)}]}
        except (json.JSONDecodeError, TypeError):
            # Not valid JSON, treat as plain text
            new_input = {"messages": [{"role": "user", "content": str(old_input)}]}

        # Update the temporary column
        connection.execute(
            text(
                """
                UPDATE quality_assurance.input_groundtruth
                SET input_jsonb = :new_input::jsonb
                WHERE id = :record_id
            """
            ),
            {"new_input": json.dumps(new_input), "record_id": record_id},
        )

    # Step 3: Drop the old column and rename the new one
    op.drop_column("input_groundtruth", "input", schema="quality_assurance")

    # Rename input_jsonb to input
    op.execute(
        text(
            """
        ALTER TABLE quality_assurance.input_groundtruth
        RENAME COLUMN input_jsonb TO input
    """
        )
    )

    # Make it NOT NULL
    op.alter_column("input_groundtruth", "input", nullable=False, schema="quality_assurance")


def downgrade() -> None:
    # Step 1: Add a temporary VARCHAR column
    op.add_column(
        "input_groundtruth", sa.Column("input_varchar", sa.VARCHAR(), nullable=True), schema="quality_assurance"
    )

    # Step 2: Migrate data back - convert JSON messages to string
    connection = op.get_bind()
    result = connection.execute(
        text(
            """
        SELECT id, input
        FROM quality_assurance.input_groundtruth
        WHERE input IS NOT NULL
    """
        )
    )

    for row in result:
        record_id = row.id
        json_input = row.input

        # Convert JSON back to string
        try:
            if isinstance(json_input, str):
                parsed = json.loads(json_input)
            else:
                parsed = json_input

            # Extract content from messages array
            if isinstance(parsed, dict) and "messages" in parsed and isinstance(parsed["messages"], list):
                # Get the last message content
                messages = parsed["messages"]
                if messages:
                    last_message = messages[-1]
                    if isinstance(last_message, dict) and "content" in last_message:
                        string_input = last_message["content"]
                    else:
                        string_input = str(parsed)
                else:
                    string_input = str(parsed)
            else:
                string_input = str(parsed)
        except (json.JSONDecodeError, TypeError, KeyError):
            string_input = str(json_input)

        # Update the temporary column
        connection.execute(
            text(
                """
                UPDATE quality_assurance.input_groundtruth
                SET input_varchar = :string_input
                WHERE id = :record_id
            """
            ),
            {"string_input": string_input, "record_id": record_id},
        )

    # Step 3: Drop the JSONB column and rename the new one
    op.drop_column("input_groundtruth", "input", schema="quality_assurance")

    # Rename input_varchar to input
    op.execute(
        text(
            """
        ALTER TABLE quality_assurance.input_groundtruth
        RENAME COLUMN input_varchar TO input
    """
        )
    )

    # Make it NOT NULL
    op.alter_column("input_groundtruth", "input", nullable=False, schema="quality_assurance")
