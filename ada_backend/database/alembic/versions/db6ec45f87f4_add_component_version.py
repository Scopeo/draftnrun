"""add component version

Revision ID: db6ec45f87f4
Revises: 8b393d7c2c4b
Create Date: 2025-09-09 11:15:23.491087

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "db6ec45f87f4"
down_revision: Union[str, None] = "44576a0ea902"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade_fk_from_component_to_version_via_mapping(
    table_name: str,
    old_component_col: str,
    new_version_col: str,
    new_fk_name: str,
) -> None:
    """
    Replaces a FK to components(<old_component_col>) with a FK to
    component_versions(<new_version_col>) based *only* on
    release_stage_to_current_version_mappings (1:1 per component before migration).
    """
    # 1) add new nullable column
    with op.batch_alter_table(table_name) as batch:
        batch.add_column(sa.Column(new_version_col, postgresql.UUID(as_uuid=True), nullable=True))

    # 2) temp map
    tmp = f"_cv_map_{table_name}"
    op.execute(f"DROP TABLE IF EXISTS {tmp};")
    op.execute(
        f"""
        CREATE TEMP TABLE {tmp} AS
        SELECT m.component_id, m.component_version_id
        FROM release_stage_to_current_version_mappings m;
        """
    )

    # 3) backfill
    op.execute(
        f"""
        UPDATE {table_name} t
        SET {new_version_col} = m.component_version_id
        FROM {tmp} m
        WHERE t.{old_component_col} = m.component_id
          AND t.{new_version_col} IS NULL;
        """
    )

    # 4) FK constraint + NOT NULL + old column deletion
    with op.batch_alter_table(table_name) as batch:
        batch.create_foreign_key(
            new_fk_name,
            "component_versions",
            [new_version_col],
            ["id"],
            ondelete="CASCADE",
        )
        batch.alter_column(new_version_col, nullable=False)
        batch.drop_column(old_component_col)

    # 5) cleaning
    op.execute(f"DROP TABLE IF EXISTS {tmp};")


def downgrade_fk_from_version_to_component(
    table_name: str,
    old_col: str,
    new_col: str,
    fk_name_old: str,
    fk_name_new: str,
):
    """
    Replace a FK to component_versions with a FK to components during downgrade.

    Args:
        table_name: The table to modify (e.g. "component_parameter_definitions")
        old_col: The column that pointed to component_versions (e.g. "component_version_id")
        new_col: The column to restore pointing to components (e.g. "component_id")
        fk_name_old: The name of the existing FK constraint to component_versions
        fk_name_new: The name of the new FK constraint to components
    """
    # 1) Add the old column back (nullable)
    with op.batch_alter_table(table_name) as batch:
        batch.add_column(sa.Column(new_col, postgresql.UUID(as_uuid=True), nullable=True))

    # 2) Build a temporary map: version_id → component_id
    tmp = f"_cv_rev_map_{table_name}"
    op.execute(f"DROP TABLE IF EXISTS {tmp};")
    op.execute(
        f"""
        CREATE TEMP TABLE {tmp} AS
        SELECT v.id AS version_id, v.component_id
        FROM component_versions v;
        """
    )

    # 3) Backfill
    op.execute(
        f"""
        UPDATE {table_name} t
        SET {new_col} = m.component_id
        FROM {tmp} m
        WHERE t.{old_col} = m.version_id
          AND t.{new_col} IS NULL;
        """
    )

    # 4) Add FK to components, set NOT NULL, drop old FK and column
    with op.batch_alter_table(table_name) as batch:
        batch.create_foreign_key(
            fk_name_new,
            "components",
            [new_col],
            ["id"],
            ondelete="CASCADE",
        )
        batch.alter_column(new_col, nullable=False)
        batch.drop_constraint(fk_name_old, type_="foreignkey")
        batch.drop_column(old_col)

    # 5) cleanup
    op.execute(f"DROP TABLE IF EXISTS {tmp};")


def upgrade() -> None:
    op.create_table(
        "component_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "component_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("components.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version_tag", sa.String(), nullable=False),
        sa.Column("changelog", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("integration_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("integrations.id"), nullable=True),
        sa.Column(
            "default_tool_description_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tool_descriptions.id"),
            nullable=True,
        ),
        sa.Column("release_stage", sa.Text(), nullable=False, server_default="internal"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.CheckConstraint(
            "LENGTH(version_tag) - LENGTH(REPLACE(version_tag, '.', '')) = 2", name="check_version_format"
        ),
        sa.CheckConstraint("version_tag <> ''", name="check_version_not_empty"),
        sa.UniqueConstraint("component_id", "version_tag", name="uq_component_version"),
    )
    op.execute("ALTER TABLE component_versions ALTER COLUMN release_stage DROP DEFAULT;")
    op.execute(
        """
    ALTER TABLE component_versions
    ALTER COLUMN release_stage TYPE release_stage
    USING (release_stage::release_stage)
    """
    )
    op.execute(
        """
    ALTER TABLE component_versions
    ALTER COLUMN release_stage SET DEFAULT 'internal'::release_stage
    """
    )

    op.execute(
        """
        INSERT INTO component_versions (
            id,
            component_id,
            version_tag,
            changelog,
            description,
            integration_id,
            default_tool_description_id,
            release_stage,
            created_at,
            updated_at
        )
        SELECT
            c.id,
            c.id,
            '1.0.0',
            NULL,
            c.description,
            c.integration_id,
            c.default_tool_description_id,
            c.release_stage::release_stage,
            COALESCE(c.created_at, now()),
            COALESCE(c.updated_at, now())
        FROM components c;
        """
    )

    # -------------------------------------------------------------------------
    # Add ReleaseStageToCurrentVersionMapping table
    # -------------------------------------------------------------------------
    op.create_unique_constraint(
        "uq_component_versions_component_id_id",
        "component_versions",
        ["component_id", "id"],
    )
    op.create_table(
        "release_stage_to_current_version_mappings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "component_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("components.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("release_stage", sa.Text(), nullable=False),
        sa.Column("component_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(
            ["component_id", "component_version_id"],
            ["component_versions.component_id", "component_versions.id"],
            name="fk_rs_current_version",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("component_id", "release_stage", name="uq_component_release_stage"),
    )
    op.execute(
        """
    ALTER TABLE release_stage_to_current_version_mappings
    ALTER COLUMN release_stage TYPE release_stage
    USING (release_stage::release_stage)
"""
    )
    op.execute(
        """
    INSERT INTO release_stage_to_current_version_mappings
        (id, component_id, release_stage, component_version_id, created_at, updated_at)
    SELECT
        gen_random_uuid(),
        v.component_id,
        v.release_stage,
        v.id,
        COALESCE(v.created_at, now()),
        COALESCE(v.updated_at, now())
    FROM component_versions v;
    """
    )

    # component_parameter_definitions: component_id -> component_version_id
    upgrade_fk_from_component_to_version_via_mapping(
        table_name="component_parameter_definitions",
        old_component_col="component_id",
        new_version_col="component_version_id",
        new_fk_name="fk_cpd_component_version",
    )

    # comp_param_child_comps_relationships: child_component_id -> child_component_version_id
    upgrade_fk_from_component_to_version_via_mapping(
        table_name="comp_param_child_comps_relationships",
        old_component_col="child_component_id",
        new_version_col="child_component_version_id",
        new_fk_name="fk_cpccr_child_component_version",
    )

    # component_instances (if you need it): component_id -> component_version_id
    upgrade_fk_from_component_to_version_via_mapping(
        table_name="component_instances",
        old_component_col="component_id",
        new_version_col="component_version_id",
        new_fk_name="fk_component_instances_component_version",
    )

    # -------------------------------------------------------------------------
    # Cleaning : remove from components the columns that are now versioned
    # -------------------------------------------------------------------------
    with op.batch_alter_table("components") as batch:
        batch.drop_column("description")
        batch.drop_column("integration_id")
        batch.drop_column("default_tool_description_id")
        batch.drop_column("release_stage")


def downgrade() -> None:
    # -------------------------------------------------------------------------
    # Add back the columns to components that were removed in upgrade()
    # -------------------------------------------------------------------------
    release_stage_enum = sa.Enum(
        "beta", "early_access", "public", "internal", name="release_stage", native_enum=True, create_type=False
    )
    with op.batch_alter_table("components") as batch:
        batch.add_column(sa.Column("description", sa.Text(), nullable=True))
        batch.add_column(
            sa.Column(
                "integration_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("integrations.id"),
                nullable=True,
            )
        )
        batch.add_column(
            sa.Column(
                "default_tool_description_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("tool_descriptions.id"),
                nullable=True,
            )
        )
        batch.add_column(
            sa.Column(
                "release_stage",
                release_stage_enum,
                nullable=False,
                server_default="internal",
            )
        )

    downgrade_fk_from_version_to_component(
        table_name="component_parameter_definitions",
        old_col="component_version_id",
        new_col="component_id",
        fk_name_old="fk_cpd_component_version",
        fk_name_new="fk_cpd_component",
    )

    downgrade_fk_from_version_to_component(
        table_name="comp_param_child_comps_relationships",
        old_col="child_component_version_id",
        new_col="child_component_id",
        fk_name_old="fk_cpccr_child_component_version",
        fk_name_new="fk_cpccr_child_component",
    )

    downgrade_fk_from_version_to_component(
        table_name="component_instances",
        old_col="component_version_id",
        new_col="component_id",
        fk_name_old="fk_component_instances_component_version",
        fk_name_new="fk_component_instances_component",
    )

    # -------------------------------------------------------------------------
    # Revert backfill: copy from current version to components
    # -------------------------------------------------------------------------
    op.execute(
        """
        UPDATE components c
        SET
            description = v.description,
            integration_id = v.integration_id,
            default_tool_description_id = v.default_tool_description_id,
            release_stage = v.release_stage
        FROM release_stage_to_current_version_mappings m
        JOIN component_versions v ON v.id = m.component_version_id
        WHERE c.id = m.component_id;
        """
    )
    # -------------------------------------------------------------------------
    # Drop ReleaseStageToCurrentVersionMapping table
    # -------------------------------------------------------------------------
    op.drop_table("release_stage_to_current_version_mappings")

    # -------------------------------------------------------------------------
    # Drop index/constraints/table component_versions
    # -------------------------------------------------------------------------
    op.execute("DROP INDEX IF EXISTS uq_component_current_version;")
    op.drop_constraint("check_version_not_empty", "component_versions", type_="check")
    op.drop_constraint("check_version_format", "component_versions", type_="check")
    op.drop_constraint(
        "uq_component_versions_component_id_id",
        "component_versions",
        type_="unique",
    )
    op.drop_table("component_versions")
