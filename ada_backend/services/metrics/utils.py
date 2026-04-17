import json
import logging
import re
from datetime import datetime, timedelta
from typing import List, Optional, Tuple
from uuid import UUID

import numpy as np
import pandas as pd
from sqlalchemy import text

from ada_backend.database.models import CallType, EnvType
from engine.trace.sql_exporter import get_session_trace

LOGGER = logging.getLogger(__name__)

QUERY_COSTS_BASIS = """
WITH trace_costs AS (
            SELECT
                s.attributes->>'conversation_id' as conversation_id,
                s.trace_rowid,
                COALESCE(
                        SUM(
                            COALESCE(su.credits_input_token, 0) +
                            COALESCE(su.credits_output_token, 0) +
                            COALESCE(su.credits_per_call, 0)
                        ),
                        0
                    ) as cost_per_run
            FROM traces.spans s
            LEFT JOIN credits.span_usages su ON su.span_id = s.span_id
"""


SQL_COST_KPIS_ROUNDED_TAIL = """
        ), raw AS (
            SELECT
                (SELECT COALESCE(AVG(total_cost_per_run), 0)::numeric FROM run_totals) as mean_cost_per_run,
                (SELECT COALESCE(AVG(total_cost_per_conversation), 0)::numeric
                 FROM conversation_totals) as mean_cost_per_conversation
        )
        SELECT
            CASE
                WHEN raw.mean_cost_per_run = 0 OR raw.mean_cost_per_run IS NULL THEN 0
                WHEN raw.mean_cost_per_run >= 1 THEN ROUND(raw.mean_cost_per_run::numeric, 0)
                ELSE ROUND(raw.mean_cost_per_run::numeric,
                    (-(FLOOR(LOG(ABS(raw.mean_cost_per_run)))::integer) + %(significant_figures)s - 1))
            END as mean_cost_per_run,
            CASE
                WHEN raw.mean_cost_per_conversation = 0 OR raw.mean_cost_per_conversation IS NULL THEN 0
                WHEN raw.mean_cost_per_conversation >= 1 THEN ROUND(raw.mean_cost_per_conversation::numeric, 0)
                ELSE ROUND(raw.mean_cost_per_conversation::numeric,
                    (-(FLOOR(LOG(ABS(raw.mean_cost_per_conversation)))::integer) + %(significant_figures)s - 1))
            END as mean_cost_per_conversation
        FROM raw
"""


def query_trace_duration(
    project_ids: List[UUID], duration_days: int, call_type: CallType | None = None
) -> pd.DataFrame:
    start_time_offset_days = (datetime.now() - timedelta(days=duration_days)).isoformat()

    # Build the call_type filter clause
    call_type_filter = ""
    if call_type is not None:
        call_type_filter = f"AND call_type = '{call_type.value}'"

    project_id_list = "', '".join(str(project_id) for project_id in project_ids)

    query = f"""
    WITH root_spans AS (
        SELECT trace_rowid
        FROM traces.spans
        WHERE parent_id IS NULL
        AND project_id IN ('{project_id_list}')
        AND start_time > '{start_time_offset_days}'
        {call_type_filter}
    )
    SELECT s.*
    FROM traces.spans s
    WHERE s.trace_rowid IN (SELECT trace_rowid FROM root_spans)
    ORDER BY MAX(s.start_time) OVER (PARTITION BY s.trace_rowid) DESC,
             s.trace_rowid, s.start_time ASC
    """

    session = get_session_trace()
    df = pd.read_sql_query(query, session.bind)
    session.close()
    df["attributes"] = df["attributes"].apply(lambda x: json.loads(x) if isinstance(x, str) else x)
    df = df.replace({np.nan: None})
    return df


def _escape_ilike(value: str) -> str:
    return value.replace("!", "!!").replace("%", "!%").replace("_", "!_")


def query_root_trace_duration(
    project_id: UUID,
    duration_days: Optional[int] = None,
    environment: Optional[EnvType] = None,
    call_type: Optional[CallType] = None,
    graph_runner_id: Optional[UUID] = None,
    page: int = 1,
    page_size: int = 20,
    search: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
) -> Tuple[List[dict], int]:
    """Query root traces with server-side pagination.

    Returns a tuple of (rows_as_dicts, total_pages).
    Time filtering: explicit start_time/end_time take precedence over duration_days.
    """
    if start_time is None and end_time is None and duration_days is None:
        duration_days = 30

    offset = (page - 1) * page_size

    filters = f"""
        project_id = '{project_id}'
        AND parent_id IS NULL
    """
    params: dict = {}

    if start_time is not None or end_time is not None:
        if start_time is not None:
            filters += "\n        AND start_time >= :filter_start_time"
            params["filter_start_time"] = start_time.isoformat()
        if end_time is not None:
            filters += "\n        AND start_time <= :filter_end_time"
            params["filter_end_time"] = end_time.isoformat()
    elif duration_days is not None:
        start_time_offset_days = (datetime.now() - timedelta(days=duration_days)).isoformat()
        filters += f"\n        AND start_time > '{start_time_offset_days}'"
    if environment is not None:
        filters += f"\n        AND environment = '{environment.value}'"
    if call_type is not None:
        filters += f"\n        AND call_type = '{call_type.value}'"
    if graph_runner_id is not None:
        filters += f"\n        AND graph_runner_id = '{graph_runner_id}'"

    if search is not None:
        escaped = _escape_ilike(search)
        json_escaped = json.dumps(search, ensure_ascii=True)[1:-1]
        if json_escaped != search:
            json_escaped_like = _escape_ilike(json_escaped)
            filters += """
        AND EXISTS (
            SELECT 1 FROM traces.span_messages m_s
            WHERE m_s.span_id = traces.spans.span_id
            AND (m_s.input_content ILIKE :search ESCAPE '!'
                 OR m_s.input_content ILIKE :search_escaped ESCAPE '!')
        )"""
            params["search_escaped"] = f"%{json_escaped_like}%"
        else:
            filters += """
        AND EXISTS (
            SELECT 1 FROM traces.span_messages m_s
            WHERE m_s.span_id = traces.spans.span_id
            AND m_s.input_content ILIKE :search ESCAPE '!'
        )"""
        params["search"] = f"%{escaped}%"

    query = f"""
    WITH total AS (
      SELECT COUNT(*) as total_count
      FROM traces.spans
      WHERE {filters}
    ),
    paginated_roots AS (
      SELECT trace_rowid, span_id, name, span_kind, start_time, end_time,
             status_code, environment, call_type, graph_runner_id, tag_name,
             attributes->>'conversation_id' as conversation_id
      FROM traces.spans
      WHERE {filters}
      ORDER BY start_time DESC
      LIMIT {page_size} OFFSET {offset}
    ),
    trace_total_credits AS (
      SELECT
        s.trace_rowid,
        ROUND(COALESCE(SUM(COALESCE(su.credits_input_token, 0) + COALESCE(su.credits_output_token, 0) +
            COALESCE(su.credits_per_call, 0)), 0)::numeric, 0) as total_credits
      FROM traces.spans s
      LEFT JOIN credits.span_usages su ON su.span_id = s.span_id
      WHERE s.trace_rowid IN (SELECT trace_rowid FROM paginated_roots)
      GROUP BY s.trace_rowid
    )
    SELECT roots.*,
           m.input_content as raw_input_content,
           m.output_content as raw_output_content,
           COALESCE(ttc.total_credits, 0) as total_credits,
           total.total_count
    FROM paginated_roots roots
    CROSS JOIN total
    LEFT JOIN traces.span_messages m ON m.span_id = roots.span_id
    LEFT JOIN trace_total_credits ttc ON ttc.trace_rowid = roots.trace_rowid
    ORDER BY roots.start_time DESC
    """

    session = get_session_trace()
    result = session.execute(text(query), params)
    rows = [dict(row._mapping) for row in result.fetchall()]
    session.close()

    for row in rows:
        row["input_preview"] = _extract_preview(row.pop("raw_input_content", None))
        row["output_preview"] = _extract_preview(row.pop("raw_output_content", None))

    total_count = int(rows[0]["total_count"]) if rows else 0
    total_pages = max((total_count + page_size - 1) // page_size, 1)
    return rows, total_pages


_CONTENT_RE = re.compile(r'"content"\s*:\s*"((?:[^"\\]|\\.)*)"')


def _extract_preview(raw_content: str | None, max_len: int = 500) -> str:
    if not raw_content:
        return ""
    try:
        parsed = json.loads(raw_content)
        if isinstance(parsed, list) and len(parsed) > 0:
            first = parsed[0]
            if isinstance(first, dict):
                if "messages" in first:
                    messages = first["messages"]
                    if isinstance(messages, list) and messages:
                        last_msg = messages[-1]
                        if isinstance(last_msg, dict) and "content" in last_msg:
                            return str(last_msg["content"])[:max_len]
                if "content" in first:
                    return str(first["content"])[:max_len]
            return str(first)[:max_len]
        return str(parsed)[:max_len]
    except (json.JSONDecodeError, TypeError, ValueError):
        match = _CONTENT_RE.search(raw_content)
        if match:
            return match.group(1)[:max_len]
        return raw_content[:max_len]


def _safe_jsonb_first_element(raw_content: str | None) -> dict:
    if not raw_content:
        return {}
    try:
        parsed = json.loads(raw_content)
        if isinstance(parsed, list) and len(parsed) > 0:
            return parsed[0] if isinstance(parsed[0], dict) else {}
        return parsed if isinstance(parsed, dict) else {}
    except (json.JSONDecodeError, TypeError, ValueError):
        return {}


def query_trace_by_trace_id(trace_id: UUID) -> pd.DataFrame:
    # TODO: add credits per unit
    query = (
        "WITH span_credits AS ("
        "  SELECT "
        "    su.span_id, "
        "    ROUND(SUM(COALESCE(su.credits_input_token, 0) + COALESCE(su.credits_output_token, 0) + "
        "        COALESCE(su.credits_per_call, 0))::numeric, 0) as credits "
        "  FROM credits.span_usages su "
        "  JOIN traces.spans s ON s.span_id = su.span_id "
        f"  WHERE s.trace_rowid = '{trace_id}' "
        "  GROUP BY su.span_id "
        ") "
        "SELECT s.*, m.input_content, m.output_content, "
        "CASE "
        "  WHEN s.parent_id IS NULL THEN ROUND(COALESCE(SUM(sc.credits) OVER (), 0)::numeric, 0) "
        "  ELSE ROUND(COALESCE(sc.credits, 0)::numeric, 0) "
        "END as total_credits "
        "FROM traces.spans s "
        "LEFT JOIN traces.span_messages m ON m.span_id = s.span_id "
        "LEFT JOIN span_credits sc ON sc.span_id = s.span_id "
        f"WHERE s.trace_rowid = '{trace_id}' "
        "ORDER BY s.start_time ASC;"
    )
    session = get_session_trace()
    df = pd.read_sql_query(query, session.bind)
    session.close()
    df["attributes"] = df["attributes"].apply(lambda x: json.loads(x) if isinstance(x, str) else x)
    df = df.replace({np.nan: None})
    return df


def calculate_calls_per_day(df: pd.DataFrame, all_dates_df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate the number of calls per day from root spans only.

    Args:
        df: DataFrame with trace data containing 'parent_id' and 'date' columns
        all_dates_df: DataFrame with all dates in the range

    Returns:
        DataFrame with 'date' and 'count' columns, sorted by date
    """
    df_root = df[df["parent_id"].isna()].copy()
    agent_usage = df_root.groupby("date").size().reset_index(name="count")
    agent_usage = pd.merge(all_dates_df, agent_usage, on="date", how="left").fillna(0)
    agent_usage["count"] = agent_usage["count"].astype(int)
    agent_usage["date"] = pd.to_datetime(agent_usage["date"]).dt.date
    agent_usage = agent_usage.sort_values(by="date", ascending=True)
    agent_usage["date"] = agent_usage["date"].astype(str)
    return agent_usage


def count_conversations_per_day(df: pd.DataFrame, all_dates_df: pd.DataFrame) -> pd.DataFrame:
    """
    Count unique conversations per day using conversation_id when available, otherwise trace_rowid.

    For dates where conversation_id exists in attributes, use it to count unique conversations.
    For dates without conversation_id, fall back to trace_rowid (each trace is a conversation).

    Args:
        df: DataFrame with trace data containing 'parent_id', 'date', 'attributes', and 'trace_rowid' columns
        all_dates_df: DataFrame with all dates in the range

    Returns:
        DataFrame with 'date' and 'unique_conversation_ids' columns, sorted by date
    """
    df_root = df[df["parent_id"].isna()].copy()

    df_with_conversation_id = df_root[
        df_root["attributes"].apply(
            lambda x: isinstance(x, dict) and "conversation_id" in x and x["conversation_id"] is not None
        )
    ].copy()

    if not df_with_conversation_id.empty:
        df_with_conversation_id["conversation_id"] = df_with_conversation_id["attributes"].apply(
            lambda x: x.get("conversation_id")
        )
        conversation_id_usage_with_id = (
            df_with_conversation_id
            .groupby("date")["conversation_id"]
            .nunique()
            .reset_index(name="unique_conversation_ids")
        )

        dates_with_id = set(df_with_conversation_id["date"].unique())
        df_without_conversation_id = df_root[~df_root["date"].isin(dates_with_id)].copy()

        if not df_without_conversation_id.empty:
            conversation_id_usage_without_id = (
                df_without_conversation_id
                .groupby("date")["trace_rowid"]
                .nunique()
                .reset_index(name="unique_conversation_ids")
            )
            conversation_id_usage = pd.concat([conversation_id_usage_with_id, conversation_id_usage_without_id])
        else:
            conversation_id_usage = conversation_id_usage_with_id
    else:
        if not df_root.empty:
            conversation_id_usage = (
                df_root.groupby("date")["trace_rowid"].nunique().reset_index(name="unique_conversation_ids")
            )
        else:
            conversation_id_usage = pd.DataFrame(columns=["date", "unique_conversation_ids"])

    conversation_id_usage = pd.merge(all_dates_df, conversation_id_usage, on="date", how="left").fillna(0)
    conversation_id_usage["unique_conversation_ids"] = conversation_id_usage["unique_conversation_ids"].astype(int)
    conversation_id_usage["date"] = conversation_id_usage["date"].dt.date.astype(str)
    conversation_id_usage = conversation_id_usage.sort_values(by="date", ascending=True)

    return conversation_id_usage


def query_conversation_messages(trace_id: str) -> tuple[dict, dict]:
    """
    Query the most recent span with a specific trace_id and return messages.

    Args:
        trace_id: The trace ID to filter spans by

    Returns:
        Tuple of (input_messages, output_messages)
    """
    query = text(
        """
    SELECT
        m.input_content,
        m.output_content

    FROM traces.spans s
    LEFT JOIN traces.span_messages m ON m.span_id = s.span_id
    WHERE s.trace_rowid = :trace_id

    AND s.name = 'Workflow'
    ORDER BY s.start_time DESC
    """
    )

    session = get_session_trace()
    result = session.execute(query, {"trace_id": trace_id}).fetchone()
    session.close()

    if not result:
        return {}, {}

    input_payload = _safe_jsonb_first_element(result[0])
    output_payload = _safe_jsonb_first_element(result[1])

    return input_payload, output_payload
