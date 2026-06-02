from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType

MIGRATION_PATH = (
    Path(__file__).parents[1]
    / "ada_backend/database/alembic/versions/9b1f8e3a4c2d_default_completion_model_to_gpt_5_mini.py"
)


class OpRecorder:
    def __init__(self) -> None:
        self.statements: list[str] = []

    def execute(self, statement: str) -> None:
        self.statements.append(statement)


def load_migration() -> ModuleType:
    spec = spec_from_file_location("default_completion_model_to_gpt_5_mini", MIGRATION_PATH)
    assert spec
    assert spec.loader
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_upgrade_updates_claude_haiku_completion_model_defaults_to_gpt_5_mini() -> None:
    migration = load_migration()
    recorder = OpRecorder()
    migration.op = recorder

    migration.upgrade()

    statements = "\n".join(recorder.statements)
    assert "UPDATE component_parameter_definitions" in statements
    assert "SET \"default\" = 'openai:gpt-5-mini'" in statements
    assert "WHERE name = 'completion_model'" in statements
    assert "\"default\" = 'anthropic:claude-haiku-4-5'" in statements


def test_downgrade_restores_claude_haiku_completion_model_defaults() -> None:
    migration = load_migration()
    recorder = OpRecorder()
    migration.op = recorder

    migration.downgrade()

    statements = "\n".join(recorder.statements)
    assert "UPDATE component_parameter_definitions" in statements
    assert "SET \"default\" = 'anthropic:claude-haiku-4-5'" in statements
    assert "WHERE name = 'completion_model'" in statements
    assert "\"default\" = 'openai:gpt-5-mini'" in statements
