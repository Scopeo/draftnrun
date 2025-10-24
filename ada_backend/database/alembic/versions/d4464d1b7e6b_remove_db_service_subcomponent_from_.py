"""remove_db_service_subcomponent_from_react_sql_agent

Revision ID: d4464d1b7e6b
Revises: f1e79aa97806
Create Date: 2025-10-24 17:29:24.192344

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d4464d1b7e6b"
down_revision: Union[str, None] = "f1e79aa97806"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# UUIDs for the db_service parameter and its child relationship
DB_SERVICE_PARAM_ID = "3f510f8c-79e9-4cf0-abe3-880e89c9372d"
DB_SERVICE_CHILD_RELATIONSHIP_ID = "12e869f3-0465-4e47-a810-d79a4f9a7bd0"
SQL_DB_SERVICE_VERSION_ID = "4014e6bd-9d2d-4142-8bdc-6dd7d9068011"


def upgrade() -> None:
    op.execute(
        f"""
        DELETE FROM comp_param_child_comps_relationships
        WHERE id = '{DB_SERVICE_CHILD_RELATIONSHIP_ID}'
        """
    )

    # Update the parameter definition type from COMPONENT to JSON (idempotent)
    # This allows the processor to handle db_service configuration
    op.execute(
        f"""
        UPDATE component_parameter_definitions
        SET type = 'json', nullable = TRUE
        WHERE id = '{DB_SERVICE_PARAM_ID}'
        AND type != 'json'
        """
    )


def downgrade() -> None:
    # Restore the parameter type to COMPONENT (idempotent)
    op.execute(
        f"""
        UPDATE component_parameter_definitions
        SET type = 'component', nullable = FALSE
        WHERE id = '{DB_SERVICE_PARAM_ID}'
        """
    )

    op.execute(
        f"""
        INSERT INTO comp_param_child_comps_relationships (id, component_parameter_definition_id, child_component_version_id)
        SELECT '{DB_SERVICE_CHILD_RELATIONSHIP_ID}', '{DB_SERVICE_PARAM_ID}', '{SQL_DB_SERVICE_VERSION_ID}'
        WHERE NOT EXISTS (
            SELECT 1 FROM comp_param_child_comps_relationships
            WHERE id = '{DB_SERVICE_CHILD_RELATIONSHIP_ID}'
        )
        """
    )
