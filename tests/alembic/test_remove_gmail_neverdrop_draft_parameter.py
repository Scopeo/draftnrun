from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType

MIGRATION_PATH = (
    Path(__file__).parents[2]
    / "ada_backend/database/alembic/versions/2f23d1a93b76_remove_gmail_neverdrop_draft_parameter.py"
)


class OpRecorder:
    def __init__(self) -> None:
        self.statements: list[str] = []

    def execute(self, statement: str) -> None:
        self.statements.append(statement)


def load_migration() -> ModuleType:
    spec = spec_from_file_location("remove_gmail_neverdrop_draft_parameter", MIGRATION_PATH)
    assert spec
    assert spec.loader
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_upgrade_backs_up_parameter_value_costs_before_deleting_them() -> None:
    migration = load_migration()
    recorder = OpRecorder()
    migration.op = recorder

    migration.upgrade()

    statements = "\n".join(recorder.statements)
    assert f"CREATE TABLE IF NOT EXISTS credits.{migration.BACKUP_TABLE}" in statements
    assert f"INSERT INTO credits.{migration.BACKUP_TABLE}" in statements
    assert "FROM credits.parameter_value_costs" in statements
    assert "JOIN credits.costs ON costs.id = parameter_value_costs.id" in statements
    assert "DELETE FROM credits.parameter_value_costs" in statements
    assert "DELETE FROM credits.costs" in statements


def test_downgrade_restores_parameter_value_costs_from_backup() -> None:
    migration = load_migration()
    recorder = OpRecorder()
    migration.op = recorder

    migration.downgrade()

    statements = "\n".join(recorder.statements)
    assert "INSERT INTO component_parameter_definitions" in statements
    assert "INSERT INTO credits.costs" in statements
    assert "INSERT INTO credits.parameter_value_costs" in statements
    assert f"FROM credits.{migration.BACKUP_TABLE}" in statements
    assert f"DROP TABLE IF EXISTS credits.{migration.BACKUP_TABLE}" in statements
