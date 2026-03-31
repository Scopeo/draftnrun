"""Classify Alembic migration files to determine the deploy strategy.

Parses migration upgrade() functions using Python AST and categorises each
operation as additive, destructive, or breaking.  The per-file results are
combined into an overall deploy strategy:

* migrate-first  – only additive ops (add column, create table, …).
                    DB migration runs before the new code is deployed.
* code-first     – only destructive ops (drop column, drop table, …).
                    New code is deployed before the migration runs.
* breaking       – rename / type-change / mixed additive+destructive.
                    All pods are scaled to zero, migration runs, pods come back.

An explicit ``deploy_strategy`` variable in the migration file overrides
auto-detection.  Files that contain raw SQL (``op.execute`` / ``op.get_bind`` /
``op.get_context``) or data operations (``op.bulk_insert``) without a manual
override are flagged as *unclassifiable* (treated as breaking with a distinct
exit-code so CI can ask for annotation).  ``op.batch_alter_table`` context
managers are walked into so their inner ops are classified.  Any unknown
``op.*`` call is also flagged as unclassifiable.
"""

from __future__ import annotations

import ast
import json
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class OpCategory(str, Enum):
    ADDITIVE = "additive"
    DESTRUCTIVE = "destructive"
    BREAKING = "breaking"
    UNCLASSIFIABLE = "unclassifiable"


class DeployStrategy(str, Enum):
    MIGRATE_FIRST = "migrate-first"
    CODE_FIRST = "code-first"
    BREAKING = "breaking"
    NONE = "none"


ADDITIVE_OPS = frozenset({
    "add_column",
    "create_table",
    "create_index",
    "create_unique_constraint",
    "create_foreign_key",
    "create_check_constraint",
    "create_primary_key",
    "create_table_comment",
    "create_column_comment",
})

DESTRUCTIVE_OPS = frozenset({
    "drop_column",
    "drop_table",
    "drop_index",
    "drop_constraint",
    "drop_table_comment",
    "drop_column_comment",
})

BREAKING_OPS = frozenset({
    "rename_table",
})

UNCLASSIFIABLE_OPS = frozenset({
    "execute",
    "get_bind",
    "get_context",
    "bulk_insert",
})

CONTAINER_OPS = frozenset({
    "batch_alter_table",
})


@dataclass
class ClassifiedOp:
    name: str
    category: OpCategory
    reason: str


@dataclass
class FileResult:
    path: str
    strategy: DeployStrategy
    override: str | None = None
    ops: list[ClassifiedOp] = field(default_factory=list)
    has_unclassifiable: bool = False
    error: str | None = None


def _get_keyword_value(call: ast.Call, name: str) -> ast.expr | None:
    for kw in call.keywords:
        if kw.arg == name:
            return kw.value
    return None


def _is_constant(node: ast.expr, value: object) -> bool:
    return isinstance(node, ast.Constant) and node.value == value


def _has_no_usable_default(node: ast.expr | None) -> bool:
    return node is None or _is_constant(node, None)


def _classify_add_column(call: ast.Call) -> OpCategory:
    """add_column is breaking when nullable=False without server_default."""
    col_call = None
    for arg in call.args:
        if isinstance(arg, ast.Call):
            col_call = arg
            break

    nullable_node = _get_keyword_value(call, "nullable")
    if nullable_node is not None and _is_constant(nullable_node, False):
        server_default = _get_keyword_value(call, "server_default")
        if _has_no_usable_default(server_default):
            if col_call is not None:
                col_sd = _get_keyword_value(col_call, "server_default")
                if _has_no_usable_default(col_sd):
                    return OpCategory.BREAKING
            else:
                return OpCategory.BREAKING

    if col_call is not None:
        col_nullable = _get_keyword_value(col_call, "nullable")
        if col_nullable is not None and _is_constant(col_nullable, False):
            col_server_default = _get_keyword_value(col_call, "server_default")
            if _has_no_usable_default(col_server_default):
                return OpCategory.BREAKING

    return OpCategory.ADDITIVE


def _classify_alter_column(call: ast.Call) -> OpCategory:
    """alter_column is breaking when renaming or changing type/nullability."""
    if _get_keyword_value(call, "new_column_name") is not None:
        return OpCategory.BREAKING
    if _get_keyword_value(call, "type_") is not None:
        return OpCategory.BREAKING
    nullable = _get_keyword_value(call, "nullable")
    if nullable is not None and _is_constant(nullable, False):
        return OpCategory.BREAKING
    return OpCategory.BREAKING


_DEFAULT_TARGETS = frozenset({"op"})


def _classify_op_call(
    call: ast.Call,
    valid_targets: frozenset[str] = _DEFAULT_TARGETS,
) -> ClassifiedOp | None:
    """Classify a single ``op.<method>(...)`` or ``batch.<method>(...)`` call."""
    if not (isinstance(call.func, ast.Attribute) and isinstance(call.func.value, ast.Name)):
        return None
    target = call.func.value.id
    if target not in valid_targets:
        return None

    method = call.func.attr

    if method == "add_column":
        cat = _classify_add_column(call)
        reason = "nullable=False without server_default" if cat == OpCategory.BREAKING else "add_column"
        return ClassifiedOp(name=f"{target}.{method}", category=cat, reason=reason)

    if method == "alter_column":
        return ClassifiedOp(
            name=f"{target}.{method}",
            category=_classify_alter_column(call),
            reason="alter_column is conservatively breaking",
        )

    if method in ADDITIVE_OPS:
        return ClassifiedOp(name=f"{target}.{method}", category=OpCategory.ADDITIVE, reason=method)

    if method in DESTRUCTIVE_OPS:
        return ClassifiedOp(name=f"{target}.{method}", category=OpCategory.DESTRUCTIVE, reason=method)

    if method in BREAKING_OPS:
        return ClassifiedOp(name=f"{target}.{method}", category=OpCategory.BREAKING, reason=method)

    if method in UNCLASSIFIABLE_OPS:
        return ClassifiedOp(
            name=f"{target}.{method}", category=OpCategory.UNCLASSIFIABLE, reason="raw SQL / data modification",
        )

    if method in CONTAINER_OPS:
        return None

    return ClassifiedOp(
        name=f"{target}.{method}", category=OpCategory.UNCLASSIFIABLE, reason=f"unknown op: {method}",
    )


def _find_batch_aliases(body: list[ast.stmt]) -> set[str]:
    """Find variable names bound to ``op.batch_alter_table(...)``."""
    aliases: set[str] = set()
    for node in ast.walk(ast.Module(body=body, type_ignores=[])):
        if not isinstance(node, ast.With):
            continue
        for item in node.items:
            ctx = item.context_expr
            if (
                isinstance(ctx, ast.Call)
                and isinstance(ctx.func, ast.Attribute)
                and isinstance(ctx.func.value, ast.Name)
                and ctx.func.value.id == "op"
                and ctx.func.attr == "batch_alter_table"
                and isinstance(item.optional_vars, ast.Name)
            ):
                aliases.add(item.optional_vars.id)
    return aliases


def _find_upgrade_body(tree: ast.Module) -> list[ast.stmt] | None:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "upgrade":
            return node.body
    return None


def _extract_deploy_strategy_override(tree: ast.Module) -> str | None:
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == "deploy_strategy" and isinstance(node.value, ast.Constant):
                return node.value.value
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "deploy_strategy":
                    if isinstance(node.value, ast.Constant):
                        return node.value.value
    return None


VALID_STRATEGIES = {s.value for s in DeployStrategy} - {DeployStrategy.NONE.value}


def classify_file(path: str) -> FileResult:
    try:
        source = Path(path).read_text()
    except (OSError, UnicodeDecodeError) as exc:
        return FileResult(
            path=path,
            strategy=DeployStrategy.BREAKING,
            has_unclassifiable=True,
            error=f"{type(exc).__name__}: {exc}",
        )
    tree = ast.parse(source, filename=path)

    override = _extract_deploy_strategy_override(tree)
    if override is not None:
        if override not in VALID_STRATEGIES:
            return FileResult(
                path=path,
                strategy=DeployStrategy.BREAKING,
                override=override,
                ops=[ClassifiedOp(
                    name="deploy_strategy", category=OpCategory.UNCLASSIFIABLE, reason=f"invalid: {override}",
                )],
                has_unclassifiable=True,
            )
        return FileResult(path=path, strategy=DeployStrategy(override), override=override)

    body = _find_upgrade_body(tree)
    if body is None:
        return FileResult(path=path, strategy=DeployStrategy.NONE)

    batch_aliases = _find_batch_aliases(body)
    valid_targets = frozenset({"op"} | batch_aliases) if batch_aliases else _DEFAULT_TARGETS

    ops: list[ClassifiedOp] = []
    for node in ast.walk(ast.Module(body=body, type_ignores=[])):
        if isinstance(node, ast.Call):
            classified = _classify_op_call(node, valid_targets)
            if classified:
                ops.append(classified)

    if not ops:
        return FileResult(path=path, strategy=DeployStrategy.NONE)

    categories = {op.category for op in ops}
    has_unclassifiable = OpCategory.UNCLASSIFIABLE in categories

    if OpCategory.BREAKING in categories:
        strategy = DeployStrategy.BREAKING
    elif OpCategory.ADDITIVE in categories and OpCategory.DESTRUCTIVE in categories:
        strategy = DeployStrategy.BREAKING
    elif has_unclassifiable:
        strategy = DeployStrategy.BREAKING
    elif categories == {OpCategory.ADDITIVE}:
        strategy = DeployStrategy.MIGRATE_FIRST
    elif categories == {OpCategory.DESTRUCTIVE}:
        strategy = DeployStrategy.CODE_FIRST
    else:
        strategy = DeployStrategy.BREAKING

    return FileResult(path=path, strategy=strategy, ops=ops, has_unclassifiable=has_unclassifiable)


def combine_strategies(results: list[FileResult]) -> DeployStrategy:
    """Combine per-file strategies into a single deploy strategy.

    Priority: breaking > (mixed migrate-first + code-first) > migrate-first/code-first > none.
    """
    strategies = {r.strategy for r in results}
    strategies.discard(DeployStrategy.NONE)

    if not strategies:
        return DeployStrategy.NONE
    if DeployStrategy.BREAKING in strategies:
        return DeployStrategy.BREAKING
    if DeployStrategy.MIGRATE_FIRST in strategies and DeployStrategy.CODE_FIRST in strategies:
        return DeployStrategy.BREAKING
    if strategies == {DeployStrategy.MIGRATE_FIRST}:
        return DeployStrategy.MIGRATE_FIRST
    if strategies == {DeployStrategy.CODE_FIRST}:
        return DeployStrategy.CODE_FIRST
    return DeployStrategy.BREAKING


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if not args:
        print("Usage: classify_migration.py <file1.py> [file2.py ...]", file=sys.stderr)
        return 2

    results: list[FileResult] = []
    for path in args:
        results.append(classify_file(path))

    overall = combine_strategies(results)
    has_unclassifiable = any(r.has_unclassifiable for r in results)

    output = {
        "strategy": overall.value,
        "has_unclassifiable": has_unclassifiable,
        "files": {
            r.path: {
                "strategy": r.strategy.value,
                "override": r.override,
                "has_unclassifiable": r.has_unclassifiable,
                "error": r.error,
                "ops": [{"name": op.name, "category": op.category.value, "reason": op.reason} for op in r.ops],
            }
            for r in results
        },
    }

    print(json.dumps(output, indent=2))

    if has_unclassifiable:
        return 3

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
