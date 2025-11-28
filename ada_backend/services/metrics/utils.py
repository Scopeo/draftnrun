from datetime import timedelta, datetime
from uuid import UUID
import logging
import json

import numpy as np
import pandas as pd
from sqlalchemy import text

from ada_backend.database.models import CallType
from engine.trace.sql_exporter import get_session_trace

LOGGER = logging.getLogger(__name__)


def query_daily_credits(
    project_id: UUID,
    duration_days: int,
    call_type: CallType | None = None,
) -> pd.DataFrame:
    """
    Query daily LLM credits usage for a project using SQL.

    Args:
        project_id: The project ID to calculate credits for
        duration_days: Number of days to look back
        call_type: Optional filter for specific call types

    Returns:
        DataFrame with 'date', 'input_credits', 'output_credits' columns
    """
    start_time = (datetime.now() - timedelta(days=duration_days)).isoformat()

    call_type_filter = ""
    if call_type is not None:
        call_type_filter = f"AND s.call_type = '{call_type.value}'"

    query = f"""
        SELECT
            DATE(s.start_time) as date,
            COALESCE(SUM(s.llm_token_count_prompt * COALESCE(co.credits_per_input_token, 0)), 0) as input_credits,
            COALESCE(SUM(s.llm_token_count_completion * COALESCE(co.credits_per_output_token, 0)), 0) as output_credits
        FROM traces.spans s
        LEFT JOIN llm_models lm ON s.model_id = lm.id
        LEFT JOIN credits.llm_costs lc ON lm.id = lc.llm_model_id
        LEFT JOIN credits.costs co ON lc.id = co.id
        WHERE s.project_id = '{project_id}'
        AND s.start_time > '{start_time}'
        {call_type_filter}
        GROUP BY DATE(s.start_time)
        ORDER BY date ASC
    """

    session = get_session_trace()
    try:
        df = pd.read_sql_query(query, session.bind)
    finally:
        session.close()

    return df


def query_daily_component_credits(
    project_id: UUID,
    duration_days: int,
    call_type: CallType | None = None,
) -> pd.DataFrame:
    """
    Query daily component credits usage for a project based on duration (seconds) using SQL.

    Calculates credits based on span duration * credits_per_second + credits_per_call for each component.

    Args:
        project_id: The project ID to calculate credits for
        duration_days: Number of days to look back
        call_type: Optional filter for specific call types

    Returns:
        DataFrame with 'date', 'component_credits' columns
    """
    start_time = (datetime.now() - timedelta(days=duration_days)).isoformat()

    call_type_filter = ""
    if call_type is not None:
        call_type_filter = f"AND s.call_type = '{call_type.value}'"

    query = f"""
        SELECT
            DATE(s.start_time) as date,
            COALESCE(SUM(
                EXTRACT(EPOCH FROM (s.end_time - s.start_time)) * COALESCE(co.credits_per_second, 0)
                + COALESCE(co.credits_per_call, 0)
            ), 0) as component_credits
        FROM traces.spans s
        LEFT JOIN component_instances ci ON s.component_instance_id = ci.id
        LEFT JOIN credits.component_costs cc ON ci.component_version_id = cc.component_version_id
        LEFT JOIN credits.costs co ON cc.id = co.id
        WHERE s.project_id = '{project_id}'
        AND s.start_time > '{start_time}'
        AND s.component_instance_id IS NOT NULL
        {call_type_filter}
        GROUP BY DATE(s.start_time)
        ORDER BY date ASC
    """

    session = get_session_trace()
    try:
        df = pd.read_sql_query(query, session.bind)
    finally:
        session.close()

    return df


def query_total_credits(
    project_id: UUID,
    duration_days: int,
    call_type: CallType | None = None,
) -> float:
    """
    Query total credits (LLM + Component) for a project using SQL.

    Args:
        project_id: The project ID to calculate credits for
        duration_days: Number of days to look back
        call_type: Optional filter for specific call types

    Returns:
        Total credits as a float
    """
    start_time = (datetime.now() - timedelta(days=duration_days)).isoformat()

    call_type_filter = ""
    if call_type is not None:
        call_type_filter = f"AND s.call_type = '{call_type.value}'"

    query = f"""
        SELECT
            COALESCE(SUM(
                -- LLM credits (only if model_id exists and tokens are present)
                COALESCE(s.llm_token_count_prompt, 0) * COALESCE(co_llm.credits_per_input_token, 0)
                + COALESCE(s.llm_token_count_completion, 0) * COALESCE(co_llm.credits_per_output_token, 0)
            ), 0)
            + COALESCE(SUM(
                -- Component credits (only if component_instance_id exists)
                CASE
                    WHEN s.component_instance_id IS NOT NULL THEN
                        EXTRACT(EPOCH FROM (s.end_time - s.start_time)) * COALESCE(co_comp.credits_per_second, 0)
                        + COALESCE(co_comp.credits_per_call, 0)
                    ELSE 0
                END
            ), 0) as total_credits
        FROM traces.spans s
        -- LLM credits joins
        LEFT JOIN llm_models lm ON s.model_id = lm.id
        LEFT JOIN credits.llm_costs lc ON lm.id = lc.llm_model_id
        LEFT JOIN credits.costs co_llm ON lc.id = co_llm.id
        -- Component credits joins
        LEFT JOIN component_instances ci ON s.component_instance_id = ci.id
        LEFT JOIN credits.component_costs cc ON ci.component_version_id = cc.component_version_id
        LEFT JOIN credits.costs co_comp ON cc.id = co_comp.id
        WHERE s.project_id = '{project_id}'
        AND s.start_time > '{start_time}'
        {call_type_filter}
    """

    session = get_session_trace()
    try:
        result = session.execute(text(query)).scalar()
        return round(float(result) if result else 0.0, 2)
    finally:
        session.close()


def query_trace_duration(project_id: UUID, duration_days: int, call_type: CallType | None = None) -> pd.DataFrame:
    start_time_offset_days = (datetime.now() - timedelta(days=duration_days)).isoformat()

    # Build the call_type filter clause
    call_type_filter = ""
    if call_type is not None:
        call_type_filter = f"AND call_type = '{call_type.value}'"

    query = f"""
    WITH root_spans AS (
        SELECT trace_rowid
        FROM traces.spans
        WHERE parent_id IS NULL
        AND project_id = '{project_id}'
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


def query_root_trace_duration(project_id: UUID, duration_days: int) -> pd.DataFrame:
    start_time_offset_days = (datetime.now() - timedelta(days=duration_days)).isoformat()

    query = f"""
    SELECT s.*, m.input_content, m.output_content
    FROM traces.spans s
    LEFT JOIN traces.span_messages m ON m.span_id = s.span_id
    WHERE s.parent_id IS NULL
    AND s.project_id = '{project_id}'
    AND s.start_time > '{start_time_offset_days}'
    ORDER BY MAX(s.start_time) OVER (PARTITION BY s.trace_rowid) DESC,
             s.trace_rowid, s.start_time ASC
    """

    session = get_session_trace()
    df = pd.read_sql_query(query, session.bind)
    session.close()
    df["attributes"] = df["attributes"].apply(lambda x: json.loads(x) if isinstance(x, str) else x)
    df = df.replace({np.nan: None})
    return df


def query_trace_by_trace_id(trace_id: UUID) -> pd.DataFrame:
    query = (
        "SELECT s.*, m.input_content,m.output_content FROM traces.spans s "
        f"LEFT JOIN traces.span_messages m ON m.span_id = s.span_id WHERE s.trace_rowid = '{trace_id}' "
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
            df_with_conversation_id.groupby("date")["conversation_id"]
            .nunique()
            .reset_index(name="unique_conversation_ids")
        )

        dates_with_id = set(df_with_conversation_id["date"].unique())
        df_without_conversation_id = df_root[~df_root["date"].isin(dates_with_id)].copy()

        if not df_without_conversation_id.empty:
            conversation_id_usage_without_id = (
                df_without_conversation_id.groupby("date")["trace_rowid"]
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
        (m.input_content::jsonb->0) as input_payload,
        (m.output_content::jsonb->0) as output_payload

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

    input_payload = result[0] if result[0] else {}
    output_payload = result[1] if result[1] else {}

    return input_payload, output_payload
