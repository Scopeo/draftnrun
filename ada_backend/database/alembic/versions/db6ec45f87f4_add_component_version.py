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
down_revision: Union[str, None] = "8b393d7c2c4b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


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
        sa.Column("version", sa.String(), nullable=False),
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
        sa.CheckConstraint("LENGTH(version) - LENGTH(REPLACE(version, '.', '')) = 2", name="check_version_format"),
        sa.CheckConstraint("version <> ''", name="check_version_not_empty"),
        sa.UniqueConstraint("component_id", "version", name="uq_component_version"),
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
        f"""
        INSERT INTO component_versions (
            id,
            component_id,
            version,
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
            gen_random_uuid(),
            c.id ,
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

    with op.batch_alter_table("component_parameter_definitions") as batch:
        batch.add_column(sa.Column("component_version_id", postgresql.UUID(as_uuid=True), nullable=True))

    # mapping component_id -> current version_id
    op.execute("DROP TABLE IF EXISTS _cv_map_defs;")
    op.execute(
        """
        CREATE TEMP TABLE _cv_map_defs AS
        SELECT v.component_id, v.id AS current_version_id
        FROM component_versions v
        WHERE v.is_current = true;
        """
    )

    # backfill
    # si ta colonne s'appelait différemment, adapte "component_id" ci-dessous
    op.execute(
        """
        UPDATE component_parameter_definitions d
        SET component_version_id = m.current_version_id
        FROM _cv_map_defs m
        WHERE d.component_id = m.component_id;
        """
    )
    op.execute(
        """
        UPDATE component_parameter_definitions d
        SET component_version_id = m.current_version_id
        FROM _cv_map_defs m
        WHERE d.component_id = m.component_id;
        """
    )

    with op.batch_alter_table("component_parameter_definitions") as batch:
        batch.create_foreign_key(
            "fk_cpd_component_version",
            "component_versions",
            ["component_version_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch.alter_column("component_version_id", nullable=False)
        # drop ancienne colonne maintenant remplacée
        batch.drop_column("component_id")

    op.execute("DROP TABLE IF EXISTS _cv_map_defs;")

    # -------------------------------------------------------------------------
    # 4) Migrer comp_param_child_comps_relationships → child_component_version_id
    #    (anciennement child_component_id)
    # -------------------------------------------------------------------------
    with op.batch_alter_table("comp_param_child_comps_relationships") as batch:
        batch.add_column(sa.Column("child_component_version_id", postgresql.UUID(as_uuid=True), nullable=True))

    op.execute("DROP TABLE IF EXISTS _cv_map_child;")
    op.execute(
        """
        CREATE TEMP TABLE _cv_map_child AS
        SELECT v.component_id, v.id AS current_version_id
        FROM component_versions v
        WHERE v.is_current = true;
        """
    )

    # backfill
    op.execute(
        """
        UPDATE comp_param_child_comps_relationships r
        SET child_component_version_id = m.current_version_id
        FROM _cv_map_child m
        WHERE r.child_component_id = m.component_id;
        """
    )

    with op.batch_alter_table("comp_param_child_comps_relationships") as batch:
        batch.create_foreign_key(
            "fk_cpccr_child_component_version",
            "component_versions",
            ["child_component_version_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch.alter_column("child_component_version_id", nullable=False)
        batch.drop_column("child_component_id")

    op.execute("DROP TABLE IF EXISTS _cv_map_child;")

    # -------------------------------------------------------------------------
    # 5) Nettoyage: retirer de components les colonnes désormais versionnées
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

    # -------------------------------------------------------------------------
    # 2) Revenir comp_param_child_comps_relationships : version → component
    # -------------------------------------------------------------------------
    with op.batch_alter_table("comp_param_child_comps_relationships") as batch:
        batch.add_column(sa.Column("child_component_id", postgresql.UUID(as_uuid=True), nullable=True))

    op.execute("DROP TABLE IF EXISTS _cv_rev_map_child;")
    op.execute(
        """
        CREATE TEMP TABLE _cv_rev_map_child AS
        SELECT v.id AS version_id, v.component_id
        FROM component_versions v
        WHERE v.is_current = true;
        """
    )

    op.execute(
        """
        UPDATE comp_param_child_comps_relationships r
        SET child_component_id = m.component_id
        FROM _cv_rev_map_child m
        WHERE r.child_component_version_id = m.version_id;
        """
    )

    with op.batch_alter_table("comp_param_child_comps_relationships") as batch:
        batch.create_foreign_key(
            "fk_cpccr_child_component",
            "components",
            ["child_component_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch.alter_column("child_component_id", nullable=False)
        batch.drop_constraint("fk_cpccr_child_component_version", type_="foreignkey")
        batch.drop_column("child_component_version_id")

    op.execute("DROP TABLE IF EXISTS _cv_rev_map_child;")

    # -------------------------------------------------------------------------
    # 3) Revenir component_parameter_definitions : version → component
    # -------------------------------------------------------------------------
    with op.batch_alter_table("component_parameter_definitions") as batch:
        batch.add_column(sa.Column("component_id", postgresql.UUID(as_uuid=True), nullable=True))

    op.execute("DROP TABLE IF EXISTS _cv_rev_map_defs;")
    op.execute(
        """
        CREATE TEMP TABLE _cv_rev_map_defs AS
        SELECT v.id AS version_id, v.component_id
        FROM component_versions v
        WHERE v.is_current = true;
        """
    )

    op.execute(
        """
        UPDATE component_parameter_definitions d
        SET component_id = m.component_id
        FROM _cv_rev_map_defs m
        WHERE d.component_version_id = m.version_id;
        """
    )

    with op.batch_alter_table("component_parameter_definitions") as batch:
        batch.create_foreign_key(
            "fk_cpd_component",
            "components",
            ["component_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch.alter_column("component_id", nullable=False)
        batch.drop_constraint("fk_cpd_component_version", type_="foreignkey")
        batch.drop_column("component_version_id")

    op.execute("DROP TABLE IF EXISTS _cv_rev_map_defs;")

    # -------------------------------------------------------------------------
    # 4) Reverser le backfill: recopier depuis la version courante vers components
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
    # 5) Drop index/constraints/table component_versions
    # -------------------------------------------------------------------------
    op.execute("DROP INDEX IF EXISTS uq_component_current_version;")
    op.drop_constraint("check_version_not_empty", "component_versions", type_="check")
    op.drop_constraint("check_version_format", "component_versions", type_="check")
    op.drop_table("component_versions")
