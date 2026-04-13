"""Drop port_mappings table (DRA-1120)

All wiring is now handled exclusively by field expressions. The dual-write
bridge and backfill migration b4c5d6e7f8a9 have already ensured every
port mapping has a corresponding field expression.  A safety backfill runs
first to cover any remaining gaps before the table is dropped.

Revision ID: g6h7i8j9k0l1
Revises: a2b3c4d5e6f7
Create Date: 2026-04-08
"""

import json
import logging
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

LOGGER = logging.getLogger(__name__)

revision: str = "g6h7i8j9k0l1"
down_revision: Union[str, None] = "a2b3c4d5e6f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

deploy_strategy = "code-first"


def upgrade() -> None:
    connection = op.get_bind()

    # Idempotency guard: skip if already dropped (e.g. re-running on a clean DB).
    has_table = connection.execute(
        sa.text("SELECT EXISTS (" "  SELECT FROM information_schema.tables WHERE table_name = 'port_mappings'" ")")
    ).scalar()
    if not has_table:
        return

    # Safety backfill: find any port_mapping rows that have no corresponding
    # field expression yet and create a RefNode expression for each one.
    # In practice this should be a no-op (the dual-write bridge and migration
    # b4c5d6e7f8a9 already covered all rows), but we run it defensively.
    rows = connection.execute(
        sa.text("""
            SELECT
                pm.source_instance_id,
                pm.target_instance_id,
                tpd.id    AS target_port_definition_id,
                tpd.name  AS target_port_name,
                COALESCE(spd.name, sopi.name) AS source_port_name
            FROM port_mappings pm
            JOIN port_definitions tpd
                ON tpd.id = pm.target_port_definition_id
            LEFT JOIN port_definitions spd
                ON spd.id = pm.source_port_definition_id
            LEFT JOIN port_instances sopi
                ON sopi.id = pm.source_output_port_instance_id
            WHERE NOT EXISTS (
                SELECT 1
                FROM port_instances pi
                JOIN input_port_instances ipi ON ipi.id = pi.id
                JOIN field_expressions fe     ON fe.id = ipi.field_expression_id
                WHERE pi.component_instance_id = pm.target_instance_id
                  AND pi.name = tpd.name
            )
        """)
    ).fetchall()

    for source_instance_id, target_instance_id, target_port_definition_id, target_port_name, source_port_name in rows:
        if not source_port_name:
            LOGGER.warning(
                "Skipping port_mapping backfill: source port name could not be resolved "
                "(source_instance_id=%s, target_instance_id=%s, target_port=%s). "
                "The mapping is orphaned and will be lost when port_mappings is dropped.",
                source_instance_id,
                target_instance_id,
                target_port_name,
            )
            continue

        expr_json = json.dumps({"type": "ref", "instance": str(source_instance_id), "port": source_port_name})

        fe_id = connection.execute(
            sa.text(
                "INSERT INTO field_expressions (id, expression_json) "
                "VALUES (gen_random_uuid(), CAST(:expr AS jsonb)) "
                "RETURNING id"
            ),
            {"expr": expr_json},
        ).scalar()

        existing_pi_id = connection.execute(
            sa.text(
                "SELECT pi.id FROM port_instances pi "
                "JOIN input_port_instances ipi ON ipi.id = pi.id "
                "WHERE pi.component_instance_id = :tid AND pi.name = :pname"
            ),
            {"tid": str(target_instance_id), "pname": target_port_name},
        ).scalar()

        if existing_pi_id:
            connection.execute(
                sa.text("UPDATE input_port_instances SET field_expression_id = :fid WHERE id = :pid"),
                {"fid": str(fe_id), "pid": str(existing_pi_id)},
            )
        else:
            pi_id = connection.execute(
                sa.text(
                    "INSERT INTO port_instances (id, component_instance_id, name, port_definition_id, type) "
                    "VALUES (gen_random_uuid(), :tid, :pname, :pdid, 'INPUT') "
                    "RETURNING id"
                ),
                {
                    "tid": str(target_instance_id),
                    "pname": target_port_name,
                    "pdid": str(target_port_definition_id),
                },
            ).scalar()
            connection.execute(
                sa.text("INSERT INTO input_port_instances (id, field_expression_id) VALUES (:pid, :fid)"),
                {"pid": str(pi_id), "fid": str(fe_id)},
            )

    # All wiring is now in field_expressions — the table can be dropped.
    op.drop_table("port_mappings")


def downgrade() -> None:
    # Recreate the table schema so the old code can run again if rolled back.
    # Rows are not restored: the pre-DRA-1120 code always fell back to field
    # expressions when port_mappings was empty, so the system stays functional.
    op.create_table(
        "port_mappings",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("graph_runner_id", sa.UUID(), nullable=False),
        sa.Column("source_instance_id", sa.UUID(), nullable=False),
        sa.Column("source_port_definition_id", sa.UUID(), nullable=True),
        sa.Column("target_instance_id", sa.UUID(), nullable=False),
        sa.Column("target_port_definition_id", sa.UUID(), nullable=False),
        sa.Column("dispatch_strategy", sa.String(), nullable=False),
        sa.Column("source_output_port_instance_id", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(["graph_runner_id"], ["graph_runners.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_instance_id"], ["component_instances.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_port_definition_id"], ["port_definitions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_instance_id"], ["component_instances.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_port_definition_id"], ["port_definitions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_output_port_instance_id"], ["port_instances.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_port_mappings_source_output_port_instance_id"),
        "port_mappings",
        ["source_output_port_instance_id"],
        unique=False,
    )
