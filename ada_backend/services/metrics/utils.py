import json
import logging
import math
from datetime import datetime, timedelta
from typing import List
from uuid import UUID, uuid4

import numpy as np
import pandas as pd
from sqlalchemy import text

from ada_backend.database.models import CallType
from ada_backend.schemas.chart_schema import Chart, ChartCategory, ChartData, ChartType, Dataset
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


def query_root_trace_duration(project_id: UUID, duration_days: int) -> pd.DataFrame:
    start_time_offset_days = (datetime.now() - timedelta(days=duration_days)).isoformat()

    query = f"""
    WITH relevant_spans AS (
      SELECT *
      FROM traces.spans
      WHERE project_id = '{project_id}'
      AND start_time > '{start_time_offset_days}'
    ),
    trace_total_credits AS (
      SELECT
        s.trace_rowid,
        ROUND(COALESCE(SUM(COALESCE(su.credits_input_token, 0) + COALESCE(su.credits_output_token, 0) +
            COALESCE(su.credits_per_call, 0)), 0)::numeric, 0) as total_credits
      FROM relevant_spans s
      LEFT JOIN credits.span_usages su ON su.span_id = s.span_id
      GROUP BY s.trace_rowid
    )
    SELECT s.*, m.input_content, m.output_content,
           COALESCE(ttc.total_credits, 0) as total_credits
    FROM relevant_spans s
    LEFT JOIN traces.span_messages m ON m.span_id = s.span_id
    LEFT JOIN trace_total_credits ttc ON ttc.trace_rowid = s.trace_rowid
    WHERE s.parent_id IS NULL
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


def compute_rank_bins(total: int) -> tuple[list[int], list[str]]:
    if total <= 10:
        edges = list(range(1, total + 2))
        labels = [str(i) for i in range(1, total + 1)]
        return edges, labels

    raw_width = total / 10
    edges = [math.ceil(1 + i * raw_width) for i in range(10)] + [total + 1]
    labels = []
    for i in range(len(edges) - 1):
        lo, hi = edges[i], edges[i + 1] - 1
        labels.append(str(lo) if lo == hi else f"{lo}-{hi}")
    return edges, labels


def _build_rank_chart(
    ranks: list,
    total_chunks: int,
    num_queries: int,
    title: str,
    subtitle: str,
    details: str,
) -> Chart | None:
    if not ranks:
        return None
    ranks_array = np.array(ranks)
    bins, labels = compute_rank_bins(total_chunks)
    hist, _ = np.histogram(ranks_array, bins=bins)
    bin_widths = [bins[i + 1] - bins[i] for i in range(len(bins) - 1)]
    percentages = (
        [round(count / (width * num_queries) * 100, 1) for count, width in zip(hist, bin_widths)]
        if num_queries > 0
        else [0] * len(hist)
    )
    chart_id = str(uuid4())
    return Chart(
        id=f"ranks_distribution_{chart_id}",
        type=ChartType.BAR,
        title=title,
        subtitle=subtitle,
        data=ChartData(
            labels=labels,
            datasets=[Dataset(label="Chunk usage rate", data=percentages)],
        ),
        x_axis_label="Rank",
        y_axis_label="Chunk usage rate (%)",
        category=ChartCategory.RETRIEVAL,
        details=details,
    )


def _parse_ranks_attribute(attributes: dict, key: str) -> list:
    try:
        ranks = attributes[key]
        if isinstance(ranks, str):
            ranks = eval(ranks)
        if isinstance(ranks, list) and ranks:
            return [r for r in ranks if r is not None]
    except Exception:
        pass
    return []


def get_ranks_distribution_charts(
    project_ids: List[UUID], duration_days: int, call_type: CallType | None = None
) -> list[Chart]:
    df = query_trace_duration(project_ids, duration_days, call_type)

    retrieval_ranks = []
    reranker_ranks = []
    max_total_retrieved = 0
    max_total_reranked = 0
    num_retrieval_queries = 0
    num_reranker_queries = 0

    for _, row in df.iterrows():
        attributes = row.get("attributes", {})
        if not attributes:
            continue

        if "original_retrieval_rank" in attributes:
            parsed = _parse_ranks_attribute(attributes, "original_retrieval_rank")
            if parsed:
                retrieval_ranks.extend(parsed)
                num_retrieval_queries += 1
        if "original_reranker_rank" in attributes:
            parsed = _parse_ranks_attribute(attributes, "original_reranker_rank")
            if parsed:
                reranker_ranks.extend(parsed)
                num_reranker_queries += 1

        total_retrieved = attributes.get("total_retrieved_chunks")
        if total_retrieved is not None:
            max_total_retrieved = max(max_total_retrieved, int(total_retrieved))
        total_reranked = attributes.get("total_reranked_chunks")
        if total_reranked is not None:
            max_total_reranked = max(max_total_reranked, int(total_reranked))

    if not max_total_retrieved and retrieval_ranks:
        max_total_retrieved = int(np.array(retrieval_ranks).max())
    if not max_total_reranked and reranker_ranks:
        max_total_reranked = int(np.array(reranker_ranks).max())

    charts = []

    if retrieval_ranks and num_retrieval_queries > 0:
        avg_chunks_per_query = round(len(retrieval_ranks) / num_retrieval_queries, 1)
        retrieval_chart = _build_rank_chart(
            retrieval_ranks,
            max_total_retrieved,
            num_retrieval_queries,
            title="Chunk usage by retriever ranking",
            subtitle=(
                f"{num_retrieval_queries} retrieval queries - {avg_chunks_per_query} chunks used in average per query"
            ),
            details=(
                "When someone asks a question, the retriever searches through your knowledge base "
                "and returns a list of chunks, ordered from what it thinks is most relevant (#1) "
                "to least relevant.\n\n"
                "This chart shows which positions in that list actually ended up being useful.\n\n"
                "If most useful chunks are at the top, you might try retrieving fewer chunks. "
                "If they're spread out, you likely need all of them."
            ),
        )
        if retrieval_chart:
            charts.append(retrieval_chart)

    if reranker_ranks and num_reranker_queries > 0:
        avg_chunks_per_query = round(len(reranker_ranks) / num_reranker_queries, 1)
        reranker_chart = _build_rank_chart(
            reranker_ranks,
            max_total_reranked,
            num_reranker_queries,
            title="Chunk usage by reranker ranking",
            subtitle=(
                f"{num_reranker_queries} reranker queries - {avg_chunks_per_query} chunks used in average per query"
            ),
            details=(
                "After the retriever finds chunks, the reranker takes a second look and reorders them "
                "to try to put the best answers at the top.\n\n"
                "This chart shows which positions in the reranked list actually ended up being useful.\n\n"
                "If most useful chunks are at the top, you might try reranking fewer chunks. "
                "If they're spread out, you likely need all of them."
            ),
        )
        if reranker_chart:
            charts.append(reranker_chart)

    return charts
