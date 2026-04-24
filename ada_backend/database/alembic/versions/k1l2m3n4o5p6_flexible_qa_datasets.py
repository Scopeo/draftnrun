"""Add flexible QA dataset columns: DatasetCellValue table, column_role, association_column_mappings.

Migrates existing data into the new normalized cell value table.

Revision ID: k1l2m3n4o5p6
Revises: 93189a98fdf2
Create Date: 2026-04-24
"""

import json
import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from ada_backend.database.utils import create_enum_if_not_exists

revision: str = "k1l2m3n4o5p6"
down_revision: Union[str, None] = "93189a98fdf2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

deploy_strategy = "migrate-first"

QA_SCHEMA = "quality_assurance"


def upgrade() -> None:
    create_enum_if_not_exists(op.get_bind(), ["input", "expected_output"], "column_role", schema=QA_SCHEMA)
    column_role_enum = postgresql.ENUM(
        "input", "expected_output", name="column_role", schema=QA_SCHEMA, create_type=False
    )

    op.add_column(
        "qa_dataset_metadata",
        sa.Column("default_role", column_role_enum, nullable=True),
        schema=QA_SCHEMA,
    )
    op.create_unique_constraint("uq_qa_metadata_column_id", "qa_dataset_metadata", ["column_id"], schema=QA_SCHEMA)

    op.create_table(
        "association_column_mappings",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "association_id",
            sa.UUID(),
            sa.ForeignKey(f"{QA_SCHEMA}.dataset_project_associations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "column_id",
            sa.UUID(),
            sa.ForeignKey(f"{QA_SCHEMA}.qa_dataset_metadata.column_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", column_role_enum, nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("association_id", "column_id", name="uq_association_column_mapping"),
        schema=QA_SCHEMA,
    )
    op.create_index(
        op.f("ix_quality_assurance_association_column_mappings_association_id"),
        "association_column_mappings",
        ["association_id"],
        schema=QA_SCHEMA,
    )
    op.create_index(
        op.f("ix_quality_assurance_association_column_mappings_column_id"),
        "association_column_mappings",
        ["column_id"],
        schema=QA_SCHEMA,
    )

    op.create_table(
        "dataset_cell_values",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("row_id", sa.UUID(), nullable=False),
        sa.Column(
            "column_id",
            sa.UUID(),
            sa.ForeignKey(f"{QA_SCHEMA}.qa_dataset_metadata.column_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("value", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["row_id"], [f"{QA_SCHEMA}.input_groundtruth.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("row_id", "column_id", name="uq_cell_row_column"),
        schema=QA_SCHEMA,
    )
    op.create_index(
        op.f("ix_quality_assurance_dataset_cell_values_row_id"),
        "dataset_cell_values",
        ["row_id"],
        schema=QA_SCHEMA,
    )
    op.create_index(
        op.f("ix_quality_assurance_dataset_cell_values_column_id"),
        "dataset_cell_values",
        ["column_id"],
        schema=QA_SCHEMA,
    )

    _migrate_existing_data()


def _migrate_existing_data() -> None:
    conn = op.get_bind()

    datasets = conn.execute(sa.text(f"SELECT id FROM {QA_SCHEMA}.dataset_project")).fetchall()

    for (dataset_id,) in datasets:
        existing_max = conn.execute(
            sa.text(
                f"SELECT COALESCE(MAX(column_display_position), -1) "
                f"FROM {QA_SCHEMA}.qa_dataset_metadata WHERE dataset_id = :did"
            ),
            {"did": dataset_id},
        ).scalar()

        input_col_id = uuid.uuid4()
        expected_output_col_id = uuid.uuid4()

        input_pos = existing_max + 1
        expected_output_pos = existing_max + 2

        conn.execute(
            sa.text(
                f"INSERT INTO {QA_SCHEMA}.qa_dataset_metadata "
                f"(id, dataset_id, column_id, column_name, column_display_position, default_role) "
                f"VALUES (gen_random_uuid(), :did, :cid, :cname, :cpos, :crole)"
            ),
            {"did": dataset_id, "cid": str(input_col_id), "cname": "Input", "cpos": input_pos, "crole": "input"},
        )
        conn.execute(
            sa.text(
                f"INSERT INTO {QA_SCHEMA}.qa_dataset_metadata "
                f"(id, dataset_id, column_id, column_name, column_display_position, default_role) "
                f"VALUES (gen_random_uuid(), :did, :cid, :cname, :cpos, :crole)"
            ),
            {
                "did": dataset_id,
                "cid": str(expected_output_col_id),
                "cname": "Expected Output",
                "cpos": expected_output_pos,
                "crole": "expected_output",
            },
        )

        col_name_to_id = {}
        metadata_rows = conn.execute(
            sa.text(
                f"SELECT column_id, column_name "
                f"FROM {QA_SCHEMA}.qa_dataset_metadata "
                f"WHERE dataset_id = :did AND default_role IS NULL"
            ),
            {"did": dataset_id},
        ).fetchall()
        for col_uuid, col_name in metadata_rows:
            col_name_to_id[col_name] = str(col_uuid)

        rows = conn.execute(
            sa.text(
                f"SELECT id, input, groundtruth, custom_columns "
                f"FROM {QA_SCHEMA}.input_groundtruth WHERE dataset_id = :did"
            ),
            {"did": dataset_id},
        ).fetchall()

        for row_id, input_val, groundtruth_val, custom_columns_val in rows:
            input_text = json.dumps(input_val) if input_val is not None else None
            conn.execute(
                sa.text(
                    f"INSERT INTO {QA_SCHEMA}.dataset_cell_values (id, row_id, column_id, value) "
                    f"VALUES (gen_random_uuid(), :rid, :cid, :val)"
                ),
                {"rid": row_id, "cid": str(input_col_id), "val": input_text},
            )
            conn.execute(
                sa.text(
                    f"INSERT INTO {QA_SCHEMA}.dataset_cell_values (id, row_id, column_id, value) "
                    f"VALUES (gen_random_uuid(), :rid, :cid, :val)"
                ),
                {"rid": row_id, "cid": str(expected_output_col_id), "val": groundtruth_val},
            )

            if custom_columns_val:
                for col_key, col_value in custom_columns_val.items():
                    try:
                        uuid.UUID(col_key)
                        resolved_col_id = col_key
                    except ValueError:
                        resolved_col_id = col_name_to_id.get(col_key)
                        if resolved_col_id is None:
                            continue
                    conn.execute(
                        sa.text(
                            f"INSERT INTO {QA_SCHEMA}.dataset_cell_values (id, row_id, column_id, value) "
                            f"VALUES (gen_random_uuid(), :rid, :cid, :val) "
                            f"ON CONFLICT (row_id, column_id) DO UPDATE SET value = :val"
                        ),
                        {"rid": row_id, "cid": resolved_col_id, "val": col_value},
                    )

        assoc_rows = conn.execute(
            sa.text(f"SELECT id FROM {QA_SCHEMA}.dataset_project_associations WHERE dataset_id = :did"),
            {"did": dataset_id},
        ).fetchall()
        for (assoc_id,) in assoc_rows:
            conn.execute(
                sa.text(
                    f"INSERT INTO {QA_SCHEMA}.association_column_mappings "
                    f"(id, association_id, column_id, role) "
                    f"VALUES (gen_random_uuid(), :aid, :cid, :role)"
                ),
                {"aid": assoc_id, "cid": str(input_col_id), "role": "input"},
            )
            conn.execute(
                sa.text(
                    f"INSERT INTO {QA_SCHEMA}.association_column_mappings "
                    f"(id, association_id, column_id, role) "
                    f"VALUES (gen_random_uuid(), :aid, :cid, :role)"
                ),
                {"aid": assoc_id, "cid": str(expected_output_col_id), "role": "expected_output"},
            )

    orphan_count = conn.execute(
        sa.text(
            f"SELECT COUNT(*) FROM {QA_SCHEMA}.input_groundtruth ig "
            f"WHERE NOT EXISTS ("
            f"  SELECT 1 FROM {QA_SCHEMA}.dataset_cell_values dcv "
            f"  JOIN {QA_SCHEMA}.qa_dataset_metadata m ON dcv.column_id = m.column_id "
            f"  WHERE dcv.row_id = ig.id AND m.dataset_id = ig.dataset_id AND m.default_role = 'input'"
            f") OR NOT EXISTS ("
            f"  SELECT 1 FROM {QA_SCHEMA}.dataset_cell_values dcv "
            f"  JOIN {QA_SCHEMA}.qa_dataset_metadata m ON dcv.column_id = m.column_id "
            f"  WHERE dcv.row_id = ig.id AND m.dataset_id = ig.dataset_id AND m.default_role = 'expected_output'"
            f")"
        )
    ).scalar()
    if orphan_count:
        raise RuntimeError(
            f"Migration validation failed: {orphan_count} input_groundtruth rows without cell values "
            f"for system columns (input/expected_output)"
        )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_quality_assurance_dataset_cell_values_column_id"),
        table_name="dataset_cell_values",
        schema=QA_SCHEMA,
        if_exists=True,
    )
    op.drop_index(
        op.f("ix_quality_assurance_dataset_cell_values_row_id"),
        table_name="dataset_cell_values",
        schema=QA_SCHEMA,
        if_exists=True,
    )
    op.drop_table("dataset_cell_values", schema=QA_SCHEMA, if_exists=True)

    op.drop_index(
        op.f("ix_quality_assurance_association_column_mappings_column_id"),
        table_name="association_column_mappings",
        schema=QA_SCHEMA,
        if_exists=True,
    )
    op.drop_index(
        op.f("ix_quality_assurance_association_column_mappings_association_id"),
        table_name="association_column_mappings",
        schema=QA_SCHEMA,
        if_exists=True,
    )
    op.drop_table("association_column_mappings", schema=QA_SCHEMA, if_exists=True)

    op.drop_constraint("uq_qa_metadata_column_id", "qa_dataset_metadata", schema=QA_SCHEMA, if_exists=True)
    op.execute(f"DELETE FROM {QA_SCHEMA}.qa_dataset_metadata WHERE default_role IS NOT NULL")
    op.drop_column("qa_dataset_metadata", "default_role", schema=QA_SCHEMA, if_exists=True)

    column_role_enum = postgresql.ENUM("input", "expected_output", name="column_role", schema=QA_SCHEMA)
    column_role_enum.drop(op.get_bind(), checkfirst=True)
