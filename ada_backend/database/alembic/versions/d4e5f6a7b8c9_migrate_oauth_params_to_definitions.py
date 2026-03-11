"""migrate oauth component params from connection_id to definition_id

For each active OAuthConnection that is referenced by a basic_parameter
(via a parameter definition with ui_component = 'OAuthConnection'):
1. Create an OrgVariableDefinition (type=oauth, default_value=connection_id)
2. Update basic_parameters.value from connection_id → definition_id

Revision ID: d4e5f6a7b8c9
Revises: c3e5a7b9d1f4
Create Date: 2026-03-11 00:00:00.000000

"""

import json
from typing import Sequence, Union
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "c3e5a7b9d1f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # Find all basic_parameters that reference an OAuthConnection component
    # Join through parameter_definition to get ui_component, and through
    # component_instance to trace back to the project/org.
    oauth_params = conn.execute(
        sa.text("""
            SELECT DISTINCT bp.value AS connection_id
            FROM basic_parameters bp
            JOIN component_parameter_definitions cpd ON cpd.id = bp.parameter_definition_id
            WHERE cpd.ui_component = 'OAuthConnection'
              AND bp.value IS NOT NULL
        """)
    ).fetchall()

    if not oauth_params:
        return

    connection_ids = [row.connection_id for row in oauth_params]

    # Fetch the active OAuthConnection records for these IDs
    connections = conn.execute(
        sa.text("""
            SELECT id, organization_id, provider_config_key, name
            FROM oauth_connections
            WHERE id = ANY(CAST(:ids AS uuid[]))
              AND deleted_at IS NULL
        """),
        {"ids": connection_ids},
    ).fetchall()

    if not connections:
        return

    # For each connection, create an OrgVariableDefinition and collect the mapping
    # connection_id → definition_id
    mapping = {}  # connection_id (str) → definition_id (str)

    for c in connections:
        conn_id_str = str(c.id)

        # Check if a definition already exists for this connection
        existing = conn.execute(
            sa.text("""
                SELECT id FROM org_variable_definitions
                WHERE organization_id = :org_id
                  AND type = 'oauth'
                  AND metadata->>'oauth_connection_id' = :conn_id
            """),
            {"org_id": c.organization_id, "conn_id": conn_id_str},
        ).fetchone()

        if existing:
            mapping[conn_id_str] = str(existing.id)
        else:
            def_id = uuid4()
            def_name = c.name if c.name else f"{c.provider_config_key}-connection"
            metadata = json.dumps({
                "provider_config_key": c.provider_config_key,
                "oauth_connection_id": conn_id_str,
            })
            conn.execute(
                sa.text("""
                    INSERT INTO org_variable_definitions
                        (id, organization_id, name, type, default_value, description,
                         required, metadata, editable, display_order)
                    VALUES
                        (:id, :org_id, :name, 'oauth', :default_value, :description,
                         false, CAST(:metadata AS jsonb), false, 0)
                    ON CONFLICT ON CONSTRAINT uq_org_variable_definition DO UPDATE
                        SET default_value = EXCLUDED.default_value,
                            metadata = EXCLUDED.metadata
                """),
                {
                    "id": def_id,
                    "org_id": c.organization_id,
                    "name": def_name,
                    "default_value": conn_id_str,
                    "description": f"OAuth connection for {c.provider_config_key}",
                    "metadata": metadata,
                },
            )
            mapping[conn_id_str] = str(def_id)

    # Update basic_parameters: swap connection_id → definition_id
    for old_val, new_val in mapping.items():
        conn.execute(
            sa.text("""
                UPDATE basic_parameters
                SET value = :new_val
                FROM component_parameter_definitions cpd
                WHERE basic_parameters.parameter_definition_id = cpd.id
                  AND cpd.ui_component = 'OAuthConnection'
                  AND basic_parameters.value = :old_val
            """),
            {"old_val": old_val, "new_val": new_val},
        )


def downgrade() -> None:
    conn = op.get_bind()

    # Reverse: swap definition_id back to connection_id using metadata
    oauth_defs = conn.execute(
        sa.text("""
            SELECT id, default_value
            FROM org_variable_definitions
            WHERE type = 'oauth'
              AND default_value IS NOT NULL
        """)
    ).fetchall()

    for defn in oauth_defs:
        def_id_str = str(defn.id)
        conn_id_str = defn.default_value

        conn.execute(
            sa.text("""
                UPDATE basic_parameters
                SET value = :conn_id
                FROM component_parameter_definitions cpd
                WHERE basic_parameters.parameter_definition_id = cpd.id
                  AND cpd.ui_component = 'OAuthConnection'
                  AND basic_parameters.value = :def_id
            """),
            {"conn_id": conn_id_str, "def_id": def_id_str},
        )

    # Delete the auto-created definitions
    conn.execute(
        sa.text("""
            DELETE FROM org_variable_definitions
            WHERE type = 'oauth'
              AND metadata->>'oauth_connection_id' IS NOT NULL
              AND editable = false
        """)
    )
