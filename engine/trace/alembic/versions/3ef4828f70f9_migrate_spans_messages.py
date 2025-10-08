"""migrate spans messages

Revision ID: 3ef4828f70f9
Revises: c4814af70804
Create Date: 2025-10-06 13:58:55.833149

"""

from typing import Sequence, Union
import json
import re

import pandas as pd
from alembic import op
import sqlalchemy as sa

from engine.trace.sql_exporter import get_session_trace


# revision identifiers, used by Alembic.
revision: str = "3ef4828f70f9"
down_revision: Union[str, None] = "c4814af70804"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# detect whether a string contains an “active” \u0000
def has_bad_u0000(s: str) -> bool:
    for m in re.finditer(r"(\\+)[uU]0000", s):
        if len(m.group(1)) % 2 == 1:  # nombre impair de backslashes => escape actif
            return True
    return False


# 2) neutralize any sequence \u0000 with an odd number of backslashes
def neutralize_u0000(s: str) -> str:
    def _repl(m):
        bs = m.group(1)
        # if odd, add a backslash to make it even => \\\\u0000 (literal)
        if len(bs) % 2 == 1:
            return bs + "\\\\u0000"
        return m.group(0)

    # remove the actual NUL if it exists (U+0000), option: replace with U+FFFD
    s = s.replace("\x00", "")  # ou '\uFFFD'
    s = re.sub(r"(\\+)[uU]0000", _repl, s)
    return s


# 3) recursive JSON cleaning (handles dict/list + JSON-embedded-in-string)
def sanitize_json(obj):
    if isinstance(obj, dict):
        return {sanitize_json(k): sanitize_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize_json(v) for v in obj]
    if isinstance(obj, str):
        s = neutralize_u0000(obj)
        # if the string looks like JSON, we try to open it, clean it up, and then re-encode it
        if s and s.lstrip()[:1] in "{[":
            try:
                inner = json.loads(s)
                inner = sanitize_json(inner)
                s = json.dumps(inner, ensure_ascii=False, allow_nan=False)
                # post-dumps neutralization (in case any \u0000 were produced)
                s = neutralize_u0000(s)
            except Exception:
                pass
        return s
    return obj


def to_json_str_super_safe(v):
    if v is None:
        return None
    if isinstance(v, str):
        try:
            data = json.loads(v)
        except Exception:
            # it's not JSON → just neutralize at the string level
            s = neutralize_u0000(v)
            # if it looks like a JSON-embedded, we leave it as is; otherwise we keep the string as is
            return s
        # data JSON → we clean it up recursively and then dumps
        data = sanitize_json(data)
        s = json.dumps(data, ensure_ascii=False, allow_nan=False)
        return neutralize_u0000(s)
    # dict/list/etc.
    data = sanitize_json(v)
    s = json.dumps(data, ensure_ascii=False, allow_nan=False)
    return neutralize_u0000(s)


def try_parse(x):
    if not isinstance(x, str):
        return True
    try:
        json.loads(x)
        return True
    except json.JSONDecodeError:
        return False


def upgrade() -> None:
    connection = op.get_bind()
    print("- Adding temporary column attributes_jsonb...")
    op.execute(
        """
        ALTER TABLE spans
        ADD COLUMN IF NOT EXISTS attributes_jsonb JSONB;
    """
    )
    total_updated = 0

    last_id = 0
    batch_size = 20000
    stmt = sa.text(
        """
        UPDATE spans
        SET attributes_jsonb = CAST(:cleaned AS jsonb)
        WHERE id = :id
    """
    )

    while True:
        df = pd.read_sql_query(
            sa.text("SELECT id, attributes FROM spans WHERE id > :last_id ORDER BY id ASC LIMIT :lim"),
            connection,
            params={"last_id": last_id, "lim": batch_size},
        )
        if df.empty:
            break
        print(f"- Processing batch starting from id={last_id} ({len(df)} lines...)")
        df["cleaned"] = df["attributes"].apply(lambda x: json.loads(x) if isinstance(x, str) else x)

        df["valid"] = df["cleaned"].apply(try_parse)
        invalid_after = df[~df["valid"]]
        print(f"→ {len(invalid_after)} lines still invalid after cleaning")

        changed = df.loc[df["attributes"] != df["cleaned"], ["id", "cleaned"]].copy()
        changed["cleaned"] = changed["cleaned"].map(to_json_str_super_safe)
        still_bad = changed["cleaned"].map(lambda s: isinstance(s, str) and has_bad_u0000(s))
        if still_bad.any():
            bad_ids = changed.loc[still_bad, "id"].head(5).tolist()
            raise ValueError(f"Still active '\\u0000' after neutralization. Example ids: {bad_ids}")

        print(f"→ {len(changed)} lines to be updated")
        if not changed.empty:
            # Conversion en liste de dictionnaires pour executemany
            rows = changed.to_dict(orient="records")

            print("- Updating rows in the database (executemany)...")
            connection.execute(
                stmt,
                rows,
            )
            total_updated += len(changed)
            last_id = int(df["id"].iloc[-1])
            print(f"→ Batch up to id={last_id}, casted: {len(changed)} lines (total: {total_updated})")
    op.execute(
        """
        UPDATE spans
        SET attributes_jsonb =
            (
              (
                (
                  (attributes_jsonb #- '{llm,input_messages}')
                  #- '{llm,output_messages}'
                )
                - 'input'
                - 'output'
              )
            )
        WHERE
              (attributes_jsonb ? 'llm')
           OR (attributes_jsonb ? 'input')
           OR (attributes_jsonb ? 'output');
        """
    )
    print("- Converting attributes (TEXT) -> JSONB using attributes_jsonb...")
    op.execute(
        """
            ALTER TABLE spans
            ALTER COLUMN attributes TYPE JSONB
            USING attributes_jsonb;
            """
    )

    print("- Dropping temporary column attributes_jsonb...")
    op.execute("ALTER TABLE spans DROP COLUMN IF EXISTS attributes_jsonb;")

    print(f"✓ Done. Total rows updated: {total_updated}")


def downgrade() -> None:
    # Step 1) Rebuild "input" and "output" keys in the attributes JSONB
    # ----------------------------------------------------------------
    # For each span that has a matching row in span_messages:
    #   - Merge the existing attributes JSONB with:
    #       input:  {"value": input_content or ""}
    #       output: {"value": output_content or ""}
    # If no matching row exists, we still ensure empty values are present.
    print("- Rebuilding input/output in attributes from span_messages...")

    # Case 1: spans with a matching row in span_messages
    op.execute(
        """
            UPDATE spans AS s
            SET attributes =
                COALESCE(s.attributes, '{}'::jsonb)
                || jsonb_build_object(
                     'input',  jsonb_build_object('value', COALESCE(sm.input_content, ''))
                   )
                || jsonb_build_object(
                     'output', jsonb_build_object('value', COALESCE(sm.output_content, ''))
                   )
            FROM span_messages sm
            WHERE sm.span_id = s.span_id;
            """
    )

    # Case 2: spans without any matching span_messages row
    # We still create empty "input" and "output" fields for consistency.
    op.execute(
        """
            UPDATE spans AS s
            SET attributes =
                COALESCE(s.attributes, '{}'::jsonb)
                || jsonb_build_object('input',  jsonb_build_object('value', ''))
                || jsonb_build_object('output', jsonb_build_object('value', ''))
            WHERE NOT EXISTS (
                SELECT 1 FROM span_messages sm WHERE sm.span_id = s.span_id
            );
            """
    )

    # Step 2) Convert attributes back from JSONB → TEXT
    # -------------------------------------------------
    # After re-injecting the input/output data, we turn the column back to text
    # to restore the previous schema.
    print("- Converting attributes (JSONB) -> TEXT...")
    op.execute(
        """
            ALTER TABLE spans
            ALTER COLUMN attributes TYPE TEXT
            USING attributes::text;
            """
    )

    print("✓ Downgrade complete (attributes now contains input/output with value strings).")
