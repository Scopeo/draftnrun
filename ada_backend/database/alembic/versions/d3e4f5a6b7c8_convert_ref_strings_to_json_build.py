"""convert @{{}} ref strings in headers/fixed_parameters to json_build AST

Existing headers and fixed_parameters field expressions may contain raw
@{{instance.port}} references embedded inside a literal JSON string.
The engine cannot resolve those at runtime because the value is treated as
an opaque literal.

This migration finds every such field expression, parses the JSON string,
replaces @{{...}} tokens with json_build placeholders, and rewrites the
expression as a proper json_build AST node that the engine can evaluate.

Revision ID: d3e4f5a6b7c8
Revises: c2396dc8b10d
Create Date: 2026-03-25 12:00:00.000000

"""

import json
import re
from typing import Any, Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "d3e4f5a6b7c8"
down_revision: Union[str, None] = "c2396dc8b10d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TOKEN_PATTERN = re.compile(
    r"@\{\{\s*([a-zA-Z0-9_-]+)(?:\.([a-zA-Z0-9_-]+)(?:::([a-zA-Z0-9_-]+))?)?\s*\}\}"
)


def _build_json_build_expression(parsed_json: Any) -> dict | None:
    refs: dict[str, dict] = {}
    counter = [0]

    def _process(value: Any) -> Any:
        if isinstance(value, str):
            matches = list(_TOKEN_PATTERN.finditer(value))
            if not matches:
                return value
            result = value
            for match in matches:
                placeholder = f"__REF_{counter[0]}__"
                counter[0] += 1
                first, port, key = match.group(1), match.group(2), match.group(3)
                if port is not None:
                    ref_json: dict[str, str] = {"type": "ref", "instance": first, "port": port}
                    if key:
                        ref_json["key"] = key
                else:
                    ref_json = {"type": "var", "name": first}
                refs[placeholder] = ref_json
                result = result.replace(match.group(0), placeholder, 1)
            return result
        if isinstance(value, dict):
            return {k: _process(v) for k, v in value.items()}
        if isinstance(value, list):
            return [_process(item) for item in value]
        return value

    template = _process(parsed_json)
    if not refs:
        return None
    return {"type": "json_build", "template": template, "refs": refs}


def _unparse_ref(ref_json: dict) -> str:
    if ref_json.get("type") == "ref":
        base = f"@{{{{{ref_json['instance']}.{ref_json['port']}}}}}"
        if ref_json.get("key"):
            base = f"@{{{{{ref_json['instance']}.{ref_json['port']}::{ref_json['key']}}}}}"
        return base
    if ref_json.get("type") == "var":
        return f"@{{{{{ref_json['name']}}}}}"
    raise ValueError(f"Unknown ref type {ref_json.get('type')!r} in {ref_json!r}")


def _restore_literal_from_json_build(expr: dict) -> dict | None:
    if expr.get("type") != "json_build":
        return None
    template = expr["template"]
    refs = expr.get("refs", {})

    placeholder_to_text = {key: _unparse_ref(ref) for key, ref in refs.items()}

    def _restore(value: Any) -> Any:
        if isinstance(value, str):
            result = value
            for placeholder, text_val in placeholder_to_text.items():
                result = result.replace(placeholder, text_val)
            return result
        if isinstance(value, dict):
            return {k: _restore(v) for k, v in value.items()}
        if isinstance(value, list):
            return [_restore(item) for item in value]
        return value

    restored = _restore(template)
    return {"type": "literal", "value": json.dumps(restored)}


def upgrade() -> None:
    connection = op.get_bind()

    tables_exist = connection.execute(
        text("""
            SELECT EXISTS (
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

    rows = connection.execute(
        text("""
            SELECT fe.id, fe.expression_json
            FROM field_expressions fe
            JOIN input_port_instances ipi ON ipi.field_expression_id = fe.id
            JOIN port_instances pi ON pi.id = ipi.id
            WHERE pi.name IN ('headers', 'fixed_parameters')
              AND fe.expression_json->>'type' = 'literal'
              AND fe.expression_json->>'value' LIKE '%@{{%'
        """)
    ).fetchall()

    if not rows:
        return

    for fe_id, expression_json in rows:
        literal_value = expression_json.get("value", "")
        try:
            parsed = json.loads(literal_value)
        except (json.JSONDecodeError, TypeError) as exc:
            print(f"[d3e4f5a6b7c8] skipping field_expression {fe_id}: {exc!r} — value: {literal_value!r:.120}")
            continue

        if not isinstance(parsed, (dict, list)):
            continue

        new_expr = _build_json_build_expression(parsed)
        if not new_expr:
            continue

        connection.execute(
            text("""
                UPDATE field_expressions
                SET expression_json = CAST(:expr_json AS jsonb)
                WHERE id = :fe_id
            """),
            {"expr_json": json.dumps(new_expr), "fe_id": str(fe_id)},
        )


def downgrade() -> None:
    connection = op.get_bind()

    tables_exist = connection.execute(
        text("""
            SELECT EXISTS (
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

    rows = connection.execute(
        text("""
            SELECT fe.id, fe.expression_json
            FROM field_expressions fe
            JOIN input_port_instances ipi ON ipi.field_expression_id = fe.id
            JOIN port_instances pi ON pi.id = ipi.id
            WHERE pi.name IN ('headers', 'fixed_parameters')
              AND fe.expression_json->>'type' = 'json_build'
        """)
    ).fetchall()

    if not rows:
        return

    for fe_id, expression_json in rows:
        restored = _restore_literal_from_json_build(expression_json)
        if not restored:
            continue

        connection.execute(
            text("""
                UPDATE field_expressions
                SET expression_json = CAST(:expr_json AS jsonb)
                WHERE id = :fe_id
            """),
            {"expr_json": json.dumps(restored), "fe_id": str(fe_id)},
        )
