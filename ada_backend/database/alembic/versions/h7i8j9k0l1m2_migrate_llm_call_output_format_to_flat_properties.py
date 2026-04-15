"""Migrate LLM Call output_format from OpenAI structured output format to flat properties.

Unifies the output_format parameter between LLM Call and AI Agent. Existing
LLM Call output_format values stored as OpenAI format
({"name": ..., "schema": {"properties": {...}}}) are rewritten to just the
flat properties dict ({"answer": {"type": "string"}, ...}).

deploy_strategy = "migrate-first"

Revision ID: h7i8j9k0l1m2
Revises: g1h2i3j4k5l6
Create Date: 2026-04-15
"""

import json
import logging
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

LOGGER = logging.getLogger(__name__)

revision: str = "h7i8j9k0l1m2"
down_revision: Union[str, None] = "g1h2i3j4k5l6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

deploy_strategy = "migrate-first"

LLM_CALL_COMPONENT_VERSION_ID = "7a039611-49b3-4bfd-b09b-c0f93edf3b79"


def upgrade() -> None:
    bind = op.get_bind()

    rows = bind.execute(
        sa.text("""
            SELECT fe.id, fe.expression_json
            FROM field_expressions fe
            JOIN input_port_instances ipi ON ipi.field_expression_id = fe.id
            JOIN port_instances pi ON pi.id = ipi.id
            WHERE pi.name = 'output_format'
              AND pi.component_instance_id IN (
                  SELECT id FROM component_instances
                  WHERE component_version_id = CAST(:version_id AS uuid)
              )
              AND fe.expression_json->>'type' = 'literal'
        """),
        {"version_id": LLM_CALL_COMPONENT_VERSION_ID},
    ).fetchall()

    migrated = 0
    for fe_id, expression_json in rows:
        literal_value_str = expression_json.get("value") if isinstance(expression_json, dict) else None
        if not literal_value_str:
            continue

        try:
            parsed = json.loads(literal_value_str)
        except (json.JSONDecodeError, TypeError):
            continue

        if not isinstance(parsed, dict):
            continue

        properties = _extract_flat_properties(parsed)
        if properties is None:
            continue

        new_literal_value = json.dumps(properties)
        new_expression = {"type": "literal", "value": new_literal_value}

        bind.execute(
            sa.text("UPDATE field_expressions SET expression_json = :expr WHERE id = :fe_id"),
            {"expr": json.dumps(new_expression), "fe_id": fe_id},
        )
        migrated += 1

    LOGGER.info(f"[h7i8j9k0l1m2] Migrated {migrated} LLM Call output_format values to flat properties format.")


def _extract_flat_properties(parsed: dict) -> dict | None:
    """Extract flat properties from an OpenAI structured output format dict.

    Returns the properties dict if the input is in OpenAI format, None otherwise
    (already flat or unrecognised).
    """
    if "schema" not in parsed or "name" not in parsed:
        return None

    schema = parsed.get("schema")
    if not isinstance(schema, dict):
        return None

    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return None

    return properties


def downgrade() -> None:
    bind = op.get_bind()

    rows = bind.execute(
        sa.text("""
            SELECT fe.id, fe.expression_json
            FROM field_expressions fe
            JOIN input_port_instances ipi ON ipi.field_expression_id = fe.id
            JOIN port_instances pi ON pi.id = ipi.id
            WHERE pi.name = 'output_format'
              AND pi.component_instance_id IN (
                  SELECT id FROM component_instances
                  WHERE component_version_id = CAST(:version_id AS uuid)
              )
              AND fe.expression_json->>'type' = 'literal'
        """),
        {"version_id": LLM_CALL_COMPONENT_VERSION_ID},
    ).fetchall()

    reverted = 0
    for fe_id, expression_json in rows:
        literal_value_str = expression_json.get("value") if isinstance(expression_json, dict) else None
        if not literal_value_str:
            continue

        try:
            parsed = json.loads(literal_value_str)
        except (json.JSONDecodeError, TypeError):
            continue

        if not isinstance(parsed, dict):
            continue

        if "schema" in parsed and "name" in parsed:
            continue

        openai_format = {
            "name": "output_schema",
            "schema": {
                "type": "object",
                "properties": parsed,
                "required": list(parsed.keys()),
                "additionalProperties": False,
            },
        }
        new_literal_value = json.dumps(openai_format)
        new_expression = {"type": "literal", "value": new_literal_value}

        bind.execute(
            sa.text("UPDATE field_expressions SET expression_json = :expr WHERE id = :fe_id"),
            {"expr": json.dumps(new_expression), "fe_id": fe_id},
        )
        reverted += 1

    LOGGER.info(f"[h7i8j9k0l1m2] Reverted {reverted} LLM Call output_format values to OpenAI format.")
