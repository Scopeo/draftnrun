"""replace db_service component with engine_url parameter for react_sql_agent

Revision ID: d4464d1b7e6b
Revises: f1e79aa97806
Create Date: 2025-10-24 17:29:24.192344

This migration changes ReactSQLAgent to use direct engine_url parameter
instead of a sub-component relationship, following the LLM service pattern.

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "d4464d1b7e6b"
down_revision: Union[str, None] = "f1e79aa97806"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# UUIDs
DB_SERVICE_PARAM_ID = "3f510f8c-79e9-4cf0-abe3-880e89c9372d"
DB_SERVICE_CHILD_RELATIONSHIP_ID = "12e869f3-0465-4e47-a810-d79a4f9a7bd0"
REACT_SQL_AGENT_VERSION_ID = "c0f1a2b3-4d5e-6f7a-8b9c-0d1e2f3a4b5c"
SQL_DB_SERVICE_VERSION_ID = "4014e6bd-9d2d-4142-8bdc-6dd7d9068011"


def upgrade() -> None:
    # Step 1: Create the new engine_url parameter definition if it doesn't exist
    # This allows the seed to upsert later without conflicts
    op.execute(
        f"""
        INSERT INTO component_parameter_definitions (id, component_version_id, name, type, nullable, is_advanced)
        SELECT '{DB_SERVICE_PARAM_ID}', '{REACT_SQL_AGENT_VERSION_ID}', 'engine_url', 'string', FALSE, FALSE
        WHERE NOT EXISTS (
            SELECT 1 FROM component_parameter_definitions
            WHERE id = '{DB_SERVICE_PARAM_ID}'
        )
        """
    )

    # Step 2: Migrate existing data - copy engine_url from db_service child components
    # to the parent react_sql_agent as a direct parameter (now uses the new definition created in Step 1)
    op.execute(
        f"""
        INSERT INTO basic_parameters (id, component_instance_id, parameter_definition_id, value, "order")
        SELECT
            gen_random_uuid(),
            parent_ci.id,
            '{DB_SERVICE_PARAM_ID}',
            child_params.value,
            NULL
        FROM component_instances parent_ci
        JOIN component_versions parent_cv ON parent_ci.component_version_id = parent_cv.id
        JOIN component_sub_inputs csi ON csi.parent_component_instance_id = parent_ci.id
        JOIN component_parameter_definitions cpd_parent ON csi.parameter_definition_id = cpd_parent.id
        JOIN component_instances child_ci ON csi.child_component_instance_id = child_ci.id
        JOIN basic_parameters child_params ON child_params.component_instance_id = child_ci.id
        JOIN component_parameter_definitions cpd_child ON child_params.parameter_definition_id = cpd_child.id
        WHERE parent_cv.id = '{REACT_SQL_AGENT_VERSION_ID}'
        AND cpd_parent.name = 'db_service'
        AND cpd_child.name = 'engine_url'
        ON CONFLICT DO NOTHING
        """
    )

    # Step 3: Remove component_sub_inputs relationships for react_sql_agent instances
    # Now that data is migrated to direct parameters, clean up the old child component relationships
    op.execute(
        f"""
        DELETE FROM component_sub_inputs csi
        WHERE csi.parent_component_instance_id IN (
            SELECT ci.id
            FROM component_instances ci
            JOIN component_versions cv ON ci.component_version_id = cv.id
            WHERE cv.id = '{REACT_SQL_AGENT_VERSION_ID}'
        )
        AND csi.parameter_definition_id IN (
            SELECT cpd.id FROM component_parameter_definitions cpd
            WHERE cpd.name = 'db_service'
        )
        """
    )

    # Step 4: Remove the component_parameter_child_relationship definition (idempotent)
    op.execute(
        f"""
        DELETE FROM comp_param_child_comps_relationships
        WHERE id = '{DB_SERVICE_CHILD_RELATIONSHIP_ID}'
        """
    )


def downgrade() -> None:
    # Remove the engine_url parameter definition (idempotent)
    op.execute(
        f"""
        DELETE FROM component_parameter_definitions
        WHERE id = '{DB_SERVICE_PARAM_ID}'
        """
    )

    # Restore the old db_service parameter definition (idempotent)
    op.execute(
        f"""
        INSERT INTO component_parameter_definitions (id, component_version_id, name, type, nullable, is_advanced)
        SELECT '{DB_SERVICE_PARAM_ID}', '{REACT_SQL_AGENT_VERSION_ID}', 'db_service', 'component', FALSE, FALSE
        WHERE NOT EXISTS (
            SELECT 1 FROM component_parameter_definitions
            WHERE id = '{DB_SERVICE_PARAM_ID}'
        )
        """
    )

    # Restore the component_parameter_child_relationship (idempotent)
    op.execute(
        f"""
        INSERT INTO comp_param_child_comps_relationships (
            id,
            component_parameter_definition_id,
            child_component_version_id
        )
        SELECT 
            '{DB_SERVICE_CHILD_RELATIONSHIP_ID}',
            '{DB_SERVICE_PARAM_ID}',
            '{SQL_DB_SERVICE_VERSION_ID}'
        WHERE NOT EXISTS (
            SELECT 1 FROM comp_param_child_comps_relationships 
            WHERE id = '{DB_SERVICE_CHILD_RELATIONSHIP_ID}'
        )
        """
    )
