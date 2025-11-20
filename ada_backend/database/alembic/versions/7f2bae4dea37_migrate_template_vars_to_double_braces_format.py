"""migrate template vars to double braces format

Revision ID: 7f2bae4dea37
Revises: b0ba5107a7e3
Create Date: 2025-11-20 19:45:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "7f2bae4dea37"
down_revision: Union[str, None] = "b0ba5107a7e3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Migrate template variables from {variable} to {{variable}} format.

    The code now escapes all single braces {} except @{{}} field expressions.
    Existing DB records using {variable} would be escaped and stop working.
    This migration converts {variable} → {{variable}} in template strings.

    Uses PostgreSQL regexp_replace() to find {variable} patterns and double them,
    while preserving @{{variable}} field expressions unchanged.
    """
    connection = op.get_bind()

    # Pattern explanation:
    # (^|[^{@]) - Start of string or any char that's not { or @ (capture group 1)
    # \{ - Opening brace
    # ([^{}]+) - One or more non-brace characters (the variable name - capture group 2)
    # \} - Closing brace
    # ($|[^}]) - End of string or any char that's not } (capture group 3)
    #
    # This avoids matching:
    # - {{variable}} (already doubled)
    # - @{{variable}} (field expressions)
    #
    # Replace with: \1{{\2}}\3 to double the braces

    pattern = r"(^|[^{@])\{([^{}]+)\}($|[^}])"
    replacement = r"\1{{\2}}\3"

    # Update basic_parameters.value
    connection.execute(
        sa.text(
            f"""
            UPDATE basic_parameters
            SET value = regexp_replace(value, '{pattern}', '{replacement}', 'g')
            WHERE value IS NOT NULL
            AND value ~ '{pattern}'
            """
        )
    )

    # Update component_global_parameters.value
    connection.execute(
        sa.text(
            f"""
            UPDATE component_global_parameters
            SET value = regexp_replace(value, '{pattern}', '{replacement}', 'g')
            WHERE value IS NOT NULL
            AND value ~ '{pattern}'
            """
        )
    )

    # Update component_parameter_definitions.default
    connection.execute(
        sa.text(
            f"""
            UPDATE component_parameter_definitions
            SET "default" = regexp_replace("default", '{pattern}', '{replacement}', 'g')
            WHERE "default" IS NOT NULL
            AND "default" ~ '{pattern}'
            """
        )
    )

    # Update quality_assurance.llm_judges.prompt_template
    connection.execute(
        sa.text(
            f"""
            UPDATE quality_assurance.llm_judges
            SET prompt_template = regexp_replace(prompt_template, '{pattern}', '{replacement}', 'g')
            WHERE prompt_template IS NOT NULL
            AND prompt_template ~ '{pattern}'
            """
        )
    )


def downgrade() -> None:
    """
    Revert template variables from {{variable}} back to {variable} format.

    This reverses the upgrade migration.
    """
    connection = op.get_bind()

    # Pattern to match {{variable}} but not @{{variable}}
    # We want to convert {{variable}} → {variable}
    # But preserve @{{variable}} field expressions

    pattern = r"(^|[^@])\{\{([^{}]+)\}\}($|[^}])"
    replacement = r"\1{\2}\3"

    # Revert basic_parameters.value
    connection.execute(
        sa.text(
            f"""
            UPDATE basic_parameters
            SET value = regexp_replace(value, '{pattern}', '{replacement}', 'g')
            WHERE value IS NOT NULL
            AND value ~ '{pattern}'
            """
        )
    )

    # Revert component_global_parameters.value
    connection.execute(
        sa.text(
            f"""
            UPDATE component_global_parameters
            SET value = regexp_replace(value, '{pattern}', '{replacement}', 'g')
            WHERE value IS NOT NULL
            AND value ~ '{pattern}'
            """
        )
    )

    # Revert component_parameter_definitions.default
    connection.execute(
        sa.text(
            f"""
            UPDATE component_parameter_definitions
            SET "default" = regexp_replace("default", '{pattern}', '{replacement}', 'g')
            WHERE "default" IS NOT NULL
            AND "default" ~ '{pattern}'
            """
        )
    )

    # Revert quality_assurance.llm_judges.prompt_template
    connection.execute(
        sa.text(
            f"""
            UPDATE quality_assurance.llm_judges
            SET prompt_template = regexp_replace(prompt_template, '{pattern}', '{replacement}', 'g')
            WHERE prompt_template IS NOT NULL
            AND prompt_template ~ '{pattern}'
            """
        )
    )
