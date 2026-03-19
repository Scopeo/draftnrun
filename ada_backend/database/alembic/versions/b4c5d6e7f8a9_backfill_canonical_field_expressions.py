"""Backfill canonical input ports with visible RefNode field expressions.

Existing graphs have invisible canonical port mappings (e.g. prev.output ->
agent.messages) but no corresponding field expression, so users cannot see or
edit the wiring in the frontend.  This migration creates a RefNode field
expression for every canonical port mapping that does not already have one.

Revision ID: b4c5d6e7f8a9
Revises: a3b4c5d6e7e8
Create Date: 2026-03-19 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = "b4c5d6e7f8a9"
down_revision: Union[str, None] = "a3b4c5d6e7e8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    connection = op.get_bind()

    # Safety: bail out if the required tables don't exist yet.
    tables_exist = connection.execute(
        text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables WHERE table_name = 'port_mappings'
            ) AND EXISTS (
                SELECT FROM information_schema.tables WHERE table_name = 'port_definitions'
            ) AND EXISTS (
                SELECT FROM information_schema.tables WHERE table_name = 'field_expressions'
            ) AND EXISTS (
                SELECT FROM information_schema.tables WHERE table_name = 'port_instances'
            ) AND EXISTS (
                SELECT FROM information_schema.tables WHERE table_name = 'input_port_instances'
            )
        """)
    ).scalar()

    if not tables_exist:
        return

    # Find canonical port mappings that do NOT already have a field expression
    # on the same (target_instance_id, target_port_name) pair.
    #
    # source_port_name comes from either the catalogue port definition or,
    # for dynamic ports, from the output port instance.
    rows = connection.execute(
        text("""
            SELECT
                pm.source_instance_id,
                pm.target_instance_id,
                tpd.name AS target_port_name,
                COALESCE(spd.name, sopi.name) AS source_port_name
            FROM port_mappings pm
            JOIN port_definitions tpd
                ON tpd.id = pm.target_port_definition_id
            LEFT JOIN port_definitions spd
                ON spd.id = pm.source_port_definition_id
            LEFT JOIN port_instances sopi
                ON sopi.id = pm.source_output_port_instance_id
            WHERE tpd.is_canonical = true
              AND NOT EXISTS (
                  SELECT 1
                  FROM port_instances pi
                  JOIN input_port_instances ipi ON ipi.id = pi.id
                  WHERE pi.component_instance_id = pm.target_instance_id
                    AND pi.name = tpd.name
                    AND ipi.field_expression_id IS NOT NULL
              )
        """)
    ).fetchall()

    if not rows:
        return

    for source_instance_id, target_instance_id, target_port_name, source_port_name in rows:
        if not source_port_name:
            continue

        expr_json = (
            '{"type": "ref", "instance": "'
            + str(source_instance_id)
            + '", "port": "'
            + source_port_name
            + '"}'
        )

        # Create the field expression record
        fe_id = connection.execute(
            text("""
                INSERT INTO field_expressions (id, expression_json)
                VALUES (gen_random_uuid(), CAST(:expr_json AS jsonb))
                RETURNING id
            """),
            {"expr_json": expr_json},
        ).scalar()

        # Check if a port_instance row already exists (without a field expression)
        existing_pi_id = connection.execute(
            text("""
                SELECT pi.id
                FROM port_instances pi
                JOIN input_port_instances ipi ON ipi.id = pi.id
                WHERE pi.component_instance_id = :target_instance_id
                  AND pi.name = :target_port_name
            """),
            {
                "target_instance_id": str(target_instance_id),
                "target_port_name": target_port_name,
            },
        ).scalar()

        if existing_pi_id:
            # Link the existing port instance to the new field expression
            connection.execute(
                text("""
                    UPDATE input_port_instances
                    SET field_expression_id = :fe_id
                    WHERE id = :pi_id
                """),
                {"fe_id": str(fe_id), "pi_id": str(existing_pi_id)},
            )
        else:
            # Create port_instance + input_port_instance rows
            pi_id = connection.execute(
                text("""
                    INSERT INTO port_instances (id, component_instance_id, name, type)
                    VALUES (gen_random_uuid(), :target_instance_id, :target_port_name, 'INPUT')
                    RETURNING id
                """),
                {
                    "target_instance_id": str(target_instance_id),
                    "target_port_name": target_port_name,
                },
            ).scalar()

            connection.execute(
                text("""
                    INSERT INTO input_port_instances (id, field_expression_id)
                    VALUES (:pi_id, :fe_id)
                """),
                {"pi_id": str(pi_id), "fe_id": str(fe_id)},
            )


def downgrade() -> None:
    connection = op.get_bind()

    tables_exist = connection.execute(
        text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables WHERE table_name = 'port_mappings'
            ) AND EXISTS (
                SELECT FROM information_schema.tables WHERE table_name = 'field_expressions'
            ) AND EXISTS (
                SELECT FROM information_schema.tables WHERE table_name = 'port_instances'
            ) AND EXISTS (
                SELECT FROM information_schema.tables WHERE table_name = 'input_port_instances'
            )
        """)
    ).scalar()

    if not tables_exist:
        return

    # Remove field expressions that were auto-generated for canonical port mappings.
    # We identify them by matching RefNode expressions whose (instance, port) pair
    # corresponds to an existing canonical port mapping.
    connection.execute(
        text("""
            DELETE FROM field_expressions fe
            USING input_port_instances ipi,
                  port_instances pi,
                  port_mappings pm,
                  port_definitions tpd
            WHERE ipi.field_expression_id = fe.id
              AND pi.id = ipi.id
              AND pi.component_instance_id = pm.target_instance_id
              AND pi.name = tpd.name
              AND tpd.id = pm.target_port_definition_id
              AND tpd.is_canonical = true
              AND fe.expression_json->>'type' = 'ref'
              AND fe.expression_json->>'instance' = pm.source_instance_id::text
        """)
    )
