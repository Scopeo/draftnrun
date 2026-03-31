from __future__ import annotations

import textwrap
from pathlib import Path

from scripts.classify_migration import (
    DeployStrategy,
    FileResult,
    OpCategory,
    classify_file,
    combine_strategies,
    main,
)


def _write_migration(tmp_path: Path, code: str, filename: str = "mig.py") -> str:
    p = tmp_path / filename
    p.write_text(textwrap.dedent(code))
    return str(p)


class TestAdditive:
    def test_add_column_nullable(self, tmp_path: Path):
        path = _write_migration(tmp_path, """
            from alembic import op
            import sqlalchemy as sa

            revision = "abc"
            down_revision = None

            def upgrade():
                op.add_column("t", sa.Column("x", sa.String(), nullable=True))

            def downgrade():
                pass
        """)
        result = classify_file(path)
        assert result.strategy == DeployStrategy.MIGRATE_FIRST
        assert not result.has_unclassifiable

    def test_create_table(self, tmp_path: Path):
        path = _write_migration(tmp_path, """
            from alembic import op
            import sqlalchemy as sa

            revision = "abc"
            down_revision = None

            def upgrade():
                op.create_table("t", sa.Column("id", sa.Integer(), primary_key=True))

            def downgrade():
                pass
        """)
        result = classify_file(path)
        assert result.strategy == DeployStrategy.MIGRATE_FIRST

    def test_create_index(self, tmp_path: Path):
        path = _write_migration(tmp_path, """
            from alembic import op

            revision = "abc"
            down_revision = None

            def upgrade():
                op.create_index("ix_t_x", "t", ["x"])

            def downgrade():
                pass
        """)
        result = classify_file(path)
        assert result.strategy == DeployStrategy.MIGRATE_FIRST


class TestDestructive:
    def test_drop_column(self, tmp_path: Path):
        path = _write_migration(tmp_path, """
            from alembic import op

            revision = "abc"
            down_revision = None

            def upgrade():
                op.drop_column("t", "x")

            def downgrade():
                pass
        """)
        result = classify_file(path)
        assert result.strategy == DeployStrategy.CODE_FIRST

    def test_drop_table(self, tmp_path: Path):
        path = _write_migration(tmp_path, """
            from alembic import op

            revision = "abc"
            down_revision = None

            def upgrade():
                op.drop_table("t")

            def downgrade():
                pass
        """)
        result = classify_file(path)
        assert result.strategy == DeployStrategy.CODE_FIRST

    def test_drop_constraint(self, tmp_path: Path):
        path = _write_migration(tmp_path, """
            from alembic import op

            revision = "abc"
            down_revision = None

            def upgrade():
                op.drop_constraint("fk_x", "t", type_="foreignkey")

            def downgrade():
                pass
        """)
        result = classify_file(path)
        assert result.strategy == DeployStrategy.CODE_FIRST


class TestBreaking:
    def test_rename_column(self, tmp_path: Path):
        path = _write_migration(tmp_path, """
            from alembic import op

            revision = "abc"
            down_revision = None

            def upgrade():
                op.alter_column("t", "old", new_column_name="new")

            def downgrade():
                pass
        """)
        result = classify_file(path)
        assert result.strategy == DeployStrategy.BREAKING

    def test_alter_column_type(self, tmp_path: Path):
        path = _write_migration(tmp_path, """
            from alembic import op
            import sqlalchemy as sa

            revision = "abc"
            down_revision = None

            def upgrade():
                op.alter_column("t", "x", type_=sa.Text())

            def downgrade():
                pass
        """)
        result = classify_file(path)
        assert result.strategy == DeployStrategy.BREAKING

    def test_alter_column_nullable_false(self, tmp_path: Path):
        path = _write_migration(tmp_path, """
            from alembic import op

            revision = "abc"
            down_revision = None

            def upgrade():
                op.alter_column("t", "x", nullable=False)

            def downgrade():
                pass
        """)
        result = classify_file(path)
        assert result.strategy == DeployStrategy.BREAKING

    def test_add_column_not_nullable_no_default(self, tmp_path: Path):
        path = _write_migration(tmp_path, """
            from alembic import op
            import sqlalchemy as sa

            revision = "abc"
            down_revision = None

            def upgrade():
                op.add_column("t", sa.Column("x", sa.String(), nullable=False))

            def downgrade():
                pass
        """)
        result = classify_file(path)
        assert result.strategy == DeployStrategy.BREAKING

    def test_add_column_not_nullable_with_default_is_additive(self, tmp_path: Path):
        path = _write_migration(tmp_path, """
            from alembic import op
            import sqlalchemy as sa

            revision = "abc"
            down_revision = None

            def upgrade():
                op.add_column("t", sa.Column("x", sa.String(), nullable=False, server_default="a"))

            def downgrade():
                pass
        """)
        result = classify_file(path)
        assert result.strategy == DeployStrategy.MIGRATE_FIRST

    def test_add_column_not_nullable_explicit_server_default_none(self, tmp_path: Path):
        path = _write_migration(tmp_path, """
            from alembic import op
            import sqlalchemy as sa

            revision = "abc"
            down_revision = None

            def upgrade():
                op.add_column("t", sa.Column("x", sa.String(), nullable=False, server_default=None))

            def downgrade():
                pass
        """)
        result = classify_file(path)
        assert result.strategy == DeployStrategy.BREAKING

    def test_batch_add_column_not_nullable_no_default(self, tmp_path: Path):
        path = _write_migration(tmp_path, """
            from alembic import op
            import sqlalchemy as sa

            revision = "abc"
            down_revision = None

            def upgrade():
                with op.batch_alter_table("t") as batch:
                    batch.add_column(sa.Column("x", sa.String(), nullable=False))

            def downgrade():
                pass
        """)
        result = classify_file(path)
        assert result.strategy == DeployStrategy.BREAKING

    def test_batch_add_column_not_nullable_explicit_server_default_none(self, tmp_path: Path):
        path = _write_migration(tmp_path, """
            from alembic import op
            import sqlalchemy as sa

            revision = "abc"
            down_revision = None

            def upgrade():
                with op.batch_alter_table("t") as batch:
                    batch.add_column(sa.Column("x", sa.String(), nullable=False, server_default=None))

            def downgrade():
                pass
        """)
        result = classify_file(path)
        assert result.strategy == DeployStrategy.BREAKING

    def test_batch_add_column_not_nullable_with_default_is_additive(self, tmp_path: Path):
        path = _write_migration(tmp_path, """
            from alembic import op
            import sqlalchemy as sa

            revision = "abc"
            down_revision = None

            def upgrade():
                with op.batch_alter_table("t") as batch:
                    batch.add_column(sa.Column("x", sa.String(), nullable=False, server_default="a"))

            def downgrade():
                pass
        """)
        result = classify_file(path)
        assert result.strategy == DeployStrategy.MIGRATE_FIRST

    def test_rename_table(self, tmp_path: Path):
        path = _write_migration(tmp_path, """
            from alembic import op

            revision = "abc"
            down_revision = None

            def upgrade():
                op.rename_table("old", "new")

            def downgrade():
                pass
        """)
        result = classify_file(path)
        assert result.strategy == DeployStrategy.BREAKING

    def test_mixed_additive_destructive(self, tmp_path: Path):
        path = _write_migration(tmp_path, """
            from alembic import op
            import sqlalchemy as sa

            revision = "abc"
            down_revision = None

            def upgrade():
                op.add_column("t", sa.Column("new_x", sa.String(), nullable=True))
                op.drop_column("t", "old_x")

            def downgrade():
                pass
        """)
        result = classify_file(path)
        assert result.strategy == DeployStrategy.BREAKING


class TestUnclassifiable:
    def test_op_execute(self, tmp_path: Path):
        path = _write_migration(tmp_path, """
            from alembic import op

            revision = "abc"
            down_revision = None

            def upgrade():
                op.execute("ALTER TYPE foo ADD VALUE 'bar'")

            def downgrade():
                pass
        """)
        result = classify_file(path)
        assert result.strategy == DeployStrategy.BREAKING
        assert result.has_unclassifiable
        assert any(op.category == OpCategory.UNCLASSIFIABLE for op in result.ops)

    def test_op_get_bind(self, tmp_path: Path):
        path = _write_migration(tmp_path, """
            from alembic import op
            import sqlalchemy as sa

            revision = "abc"
            down_revision = None

            def upgrade():
                conn = op.get_bind()
                conn.execute(sa.text("UPDATE t SET x = 1"))

            def downgrade():
                pass
        """)
        result = classify_file(path)
        assert result.has_unclassifiable


class TestManualOverride:
    def test_override_migrate_first(self, tmp_path: Path):
        path = _write_migration(tmp_path, """
            from typing import Union
            from alembic import op

            revision = "abc"
            down_revision = None
            deploy_strategy: Union[str, None] = "migrate-first"

            def upgrade():
                op.execute("ALTER TYPE foo ADD VALUE 'bar'")

            def downgrade():
                pass
        """)
        result = classify_file(path)
        assert result.strategy == DeployStrategy.MIGRATE_FIRST
        assert result.override == "migrate-first"

    def test_override_code_first(self, tmp_path: Path):
        path = _write_migration(tmp_path, """
            from typing import Union
            from alembic import op

            revision = "abc"
            down_revision = None
            deploy_strategy: Union[str, None] = "code-first"

            def upgrade():
                op.execute("DROP TABLE old_stuff")

            def downgrade():
                pass
        """)
        result = classify_file(path)
        assert result.strategy == DeployStrategy.CODE_FIRST
        assert result.override == "code-first"

    def test_override_breaking(self, tmp_path: Path):
        path = _write_migration(tmp_path, """
            from typing import Union
            from alembic import op

            revision = "abc"
            down_revision = None
            deploy_strategy: Union[str, None] = "breaking"

            def upgrade():
                op.execute("ALTER TABLE t RENAME TO t2")

            def downgrade():
                pass
        """)
        result = classify_file(path)
        assert result.strategy == DeployStrategy.BREAKING
        assert result.override == "breaking"

    def test_invalid_override_defaults_to_breaking(self, tmp_path: Path):
        path = _write_migration(tmp_path, """
            from typing import Union
            from alembic import op

            revision = "abc"
            down_revision = None
            deploy_strategy: Union[str, None] = "yolo"

            def upgrade():
                op.add_column("t", "x")

            def downgrade():
                pass
        """)
        result = classify_file(path)
        assert result.strategy == DeployStrategy.BREAKING
        assert result.has_unclassifiable is True
        assert result.override == "yolo"
        assert len(result.ops) == 1
        assert result.ops[0].category == OpCategory.UNCLASSIFIABLE
        assert "yolo" in result.ops[0].reason

    def test_override_assign_without_annotation(self, tmp_path: Path):
        path = _write_migration(tmp_path, """
            from alembic import op

            revision = "abc"
            down_revision = None
            deploy_strategy = "migrate-first"

            def upgrade():
                op.execute("SELECT 1")

            def downgrade():
                pass
        """)
        result = classify_file(path)
        assert result.strategy == DeployStrategy.MIGRATE_FIRST
        assert result.override == "migrate-first"


class TestBatchAlterTable:
    def test_batch_additive_ops(self, tmp_path: Path):
        path = _write_migration(tmp_path, """
            from alembic import op
            import sqlalchemy as sa

            revision = "abc"
            down_revision = None

            def upgrade():
                with op.batch_alter_table("t") as batch:
                    batch.add_column(sa.Column("x", sa.String(), nullable=True))
                    batch.create_foreign_key("fk_x", "other", ["x"], ["id"])

            def downgrade():
                pass
        """)
        result = classify_file(path)
        assert result.strategy == DeployStrategy.MIGRATE_FIRST
        assert not result.has_unclassifiable

    def test_batch_destructive_ops(self, tmp_path: Path):
        path = _write_migration(tmp_path, """
            from alembic import op

            revision = "abc"
            down_revision = None

            def upgrade():
                with op.batch_alter_table("t") as batch:
                    batch.drop_column("x")

            def downgrade():
                pass
        """)
        result = classify_file(path)
        assert result.strategy == DeployStrategy.CODE_FIRST

    def test_batch_mixed_ops_is_breaking(self, tmp_path: Path):
        path = _write_migration(tmp_path, """
            from alembic import op
            import sqlalchemy as sa

            revision = "abc"
            down_revision = None

            def upgrade():
                with op.batch_alter_table("t") as batch:
                    batch.add_column(sa.Column("y", sa.String(), nullable=True))
                    batch.drop_column("x")

            def downgrade():
                pass
        """)
        result = classify_file(path)
        assert result.strategy == DeployStrategy.BREAKING

    def test_batch_alter_column_is_breaking(self, tmp_path: Path):
        path = _write_migration(tmp_path, """
            from alembic import op

            revision = "abc"
            down_revision = None

            def upgrade():
                with op.batch_alter_table("t") as batch:
                    batch.alter_column("x", server_default=None)

            def downgrade():
                pass
        """)
        result = classify_file(path)
        assert result.strategy == DeployStrategy.BREAKING

    def test_batch_with_direct_ops(self, tmp_path: Path):
        path = _write_migration(tmp_path, """
            from alembic import op
            import sqlalchemy as sa

            revision = "abc"
            down_revision = None

            def upgrade():
                op.create_table("t2", sa.Column("id", sa.Integer(), primary_key=True))
                with op.batch_alter_table("t") as batch:
                    batch.drop_column("old_col")

            def downgrade():
                pass
        """)
        result = classify_file(path)
        assert result.strategy == DeployStrategy.BREAKING


class TestBulkInsert:
    def test_bulk_insert_is_unclassifiable(self, tmp_path: Path):
        path = _write_migration(tmp_path, """
            from alembic import op
            import sqlalchemy as sa

            revision = "abc"
            down_revision = None

            def upgrade():
                t = sa.table("t", sa.column("name", sa.String()))
                op.bulk_insert(t, [{"name": "a"}])

            def downgrade():
                pass
        """)
        result = classify_file(path)
        assert result.has_unclassifiable
        assert result.strategy == DeployStrategy.BREAKING
        assert any(op.category == OpCategory.UNCLASSIFIABLE for op in result.ops)


class TestGetContext:
    def test_get_context_is_unclassifiable(self, tmp_path: Path):
        path = _write_migration(tmp_path, """
            from alembic import op
            import sqlalchemy as sa

            revision = "abc"
            down_revision = None

            def upgrade():
                with op.get_context().autocommit_block():
                    op.execute("ALTER TYPE foo ADD VALUE 'bar'")

            def downgrade():
                pass
        """)
        result = classify_file(path)
        assert result.has_unclassifiable


class TestUnknownOps:
    def test_unknown_op_is_unclassifiable(self, tmp_path: Path):
        path = _write_migration(tmp_path, """
            from alembic import op

            revision = "abc"
            down_revision = None

            def upgrade():
                op.some_future_operation("t")

            def downgrade():
                pass
        """)
        result = classify_file(path)
        assert result.has_unclassifiable
        assert result.strategy == DeployStrategy.BREAKING
        assert any(op.reason.startswith("unknown op") for op in result.ops)

    def test_only_unknown_ops_not_classified_as_none(self, tmp_path: Path):
        path = _write_migration(tmp_path, """
            from alembic import op

            revision = "abc"
            down_revision = None

            def upgrade():
                op.totally_made_up("t")

            def downgrade():
                pass
        """)
        result = classify_file(path)
        assert result.strategy != DeployStrategy.NONE


class TestEmptyAndNoOps:
    def test_empty_upgrade(self, tmp_path: Path):
        path = _write_migration(tmp_path, """
            from alembic import op

            revision = "abc"
            down_revision = None

            def upgrade():
                pass

            def downgrade():
                pass
        """)
        result = classify_file(path)
        assert result.strategy == DeployStrategy.NONE

    def test_no_upgrade_function(self, tmp_path: Path):
        path = _write_migration(tmp_path, """
            revision = "abc"
            down_revision = None
        """)
        result = classify_file(path)
        assert result.strategy == DeployStrategy.NONE


class TestCombineStrategies:
    def test_all_migrate_first(self):
        results = [
            FileResult(path="a.py", strategy=DeployStrategy.MIGRATE_FIRST),
            FileResult(path="b.py", strategy=DeployStrategy.MIGRATE_FIRST),
        ]
        assert combine_strategies(results) == DeployStrategy.MIGRATE_FIRST

    def test_all_code_first(self):
        results = [
            FileResult(path="a.py", strategy=DeployStrategy.CODE_FIRST),
            FileResult(path="b.py", strategy=DeployStrategy.CODE_FIRST),
        ]
        assert combine_strategies(results) == DeployStrategy.CODE_FIRST

    def test_mixed_becomes_breaking(self):
        results = [
            FileResult(path="a.py", strategy=DeployStrategy.MIGRATE_FIRST),
            FileResult(path="b.py", strategy=DeployStrategy.CODE_FIRST),
        ]
        assert combine_strategies(results) == DeployStrategy.BREAKING

    def test_breaking_wins(self):
        results = [
            FileResult(path="a.py", strategy=DeployStrategy.MIGRATE_FIRST),
            FileResult(path="b.py", strategy=DeployStrategy.BREAKING),
        ]
        assert combine_strategies(results) == DeployStrategy.BREAKING

    def test_none_ignored(self):
        results = [
            FileResult(path="a.py", strategy=DeployStrategy.NONE),
            FileResult(path="b.py", strategy=DeployStrategy.MIGRATE_FIRST),
        ]
        assert combine_strategies(results) == DeployStrategy.MIGRATE_FIRST

    def test_all_none(self):
        results = [
            FileResult(path="a.py", strategy=DeployStrategy.NONE),
        ]
        assert combine_strategies(results) == DeployStrategy.NONE


class TestCLI:
    def test_no_args(self):
        assert main([]) == 2

    def test_additive_exit_0(self, tmp_path: Path, capsys):
        path = _write_migration(tmp_path, """
            from alembic import op
            import sqlalchemy as sa

            revision = "abc"
            down_revision = None

            def upgrade():
                op.add_column("t", sa.Column("x", sa.String(), nullable=True))

            def downgrade():
                pass
        """)
        assert main([str(path)]) == 0
        out = capsys.readouterr().out
        assert '"strategy": "migrate-first"' in out

    def test_unclassifiable_exit_3(self, tmp_path: Path, capsys):
        path = _write_migration(tmp_path, """
            from alembic import op

            revision = "abc"
            down_revision = None

            def upgrade():
                op.execute("SELECT 1")

            def downgrade():
                pass
        """)
        assert main([str(path)]) == 3
        out = capsys.readouterr().out
        assert '"has_unclassifiable": true' in out


class TestFileReadErrors:
    def test_missing_file(self, tmp_path: Path):
        path = str(tmp_path / "does_not_exist.py")
        result = classify_file(path)
        assert result.strategy == DeployStrategy.BREAKING
        assert result.has_unclassifiable
        assert result.error is not None
        assert "FileNotFoundError" in result.error

    def test_missing_file_cli_exit_3(self, capsys):
        assert main(["/tmp/no_such_migration_file.py"]) == 3
        out = capsys.readouterr().out
        assert '"error"' in out
        assert "FileNotFoundError" in out


class TestRealMigrations:
    """Smoke-test against actual migration files in the repo."""

    def test_add_default_tool_json_schema(self):
        result = classify_file(
            "ada_backend/database/alembic/versions/"
            "e4f5a6b7c8d9_add_default_tool_json_schema_to_port_definitions.py"
        )
        assert result.strategy == DeployStrategy.MIGRATE_FIRST

    def test_remove_database_name(self):
        result = classify_file(
            "ada_backend/database/alembic/versions/"
            "f35bfa8d86b7_remove_database_name_from_datasources_.py"
        )
        assert result.strategy == DeployStrategy.CODE_FIRST

    def test_rename_order(self):
        result = classify_file(
            "ada_backend/database/alembic/versions/"
            "b1c2d3e4f5a7_rename_order_to_display_order_in_component_parameter_definitions.py"
        )
        assert result.strategy == DeployStrategy.BREAKING
