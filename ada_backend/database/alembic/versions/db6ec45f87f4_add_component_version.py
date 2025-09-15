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
down_revision: Union[str, None] = "ed8f19491923"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade_fk_from_component_to_version_current(
    table_name: str,
    old_component_col: str,
    new_version_col: str,
    new_fk_name: str,
) -> None:
    """
    Replace a FK to components(<old_component_col>) with a FK to component_versions(<new_version_col>),
    mapping each row to the component's *current* version (v.is_current = true).

    Steps:
      1) Add <new_version_col> (NULL).
      2) Build temp map component_id -> current version_id.
      3) Backfill <new_version_col>.
      4) Create FK to component_versions, set NOT NULL.
      5) Drop <old_component_col>.
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
        SELECT v.component_id, v.id AS current_version_id
        FROM component_versions v
        WHERE v.is_current = true;
    """
    )

    # 3) backfill
    op.execute(
        f"""
        UPDATE {table_name} t
        SET {new_version_col} = m.current_version_id
        FROM {tmp} m
        WHERE t.{old_component_col} = m.component_id
          AND t.{new_version_col} IS NULL;
    """
    )

    # 4) FK + NOT NULL + drop old column
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

    # 5) cleanup
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
        FROM component_versions v
        WHERE v.is_current = true;
    """
    )

    # 3) Backfill
    op.execute(
        f"""
        UPDATE {table_name} t
        SET {new_col} = m.component_id
        FROM {tmp} m
        WHERE t.{old_col} = m.version_id;
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
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.text("true")),
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
        CREATE UNIQUE INDEX uq_component_current_version
        ON component_versions (component_id)
        WHERE is_current = true;
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
            is_current,
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
            TRUE,
            COALESCE(c.created_at, now()),
            COALESCE(c.updated_at, now())
        FROM components c;
        """
    )

    # component_parameter_definitions: component_id -> component_version_id
    upgrade_fk_from_component_to_version_current(
        table_name="component_parameter_definitions",
        old_component_col="component_id",
        new_version_col="component_version_id",
        new_fk_name="fk_cpd_component_version",
    )

    # comp_param_child_comps_relationships: child_component_id -> child_component_version_id
    upgrade_fk_from_component_to_version_current(
        table_name="comp_param_child_comps_relationships",
        old_component_col="child_component_id",
        new_version_col="child_component_version_id",
        new_fk_name="fk_cpccr_child_component_version",
    )

    # component_instances (if you need it): component_id -> component_version_id
    upgrade_fk_from_component_to_version_current(
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
        FROM component_versions v
        WHERE v.component_id = c.id
          AND v.is_current = true;
        """
    )

    # -------------------------------------------------------------------------
    # Drop index/constraints/table component_versions
    # -------------------------------------------------------------------------
    op.execute("DROP INDEX IF EXISTS uq_component_current_version;")
    op.drop_constraint("check_version_not_empty", "component_versions", type_="check")
    op.drop_constraint("check_version_format", "component_versions", type_="check")
    op.drop_table("component_versions")
