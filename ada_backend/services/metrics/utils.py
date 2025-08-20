from datetime import timedelta, datetime
import json
from uuid import UUID
import logging

import numpy as np
import pandas as pd

from engine.trace.sql_exporter import get_session_trace

LOGGER = logging.getLogger(__name__)


def query_trace_duration(project_id: UUID, duration_days: int) -> pd.DataFrame:
    start_time_offset_days = (datetime.now() - timedelta(days=duration_days)).isoformat()
    query = (
        f"SELECT * FROM spans WHERE start_time > '{start_time_offset_days}'"
        "ORDER BY MAX(start_time) OVER (PARTITION BY trace_rowid) DESC, "
        "trace_rowid, start_time ASC;"
    )
    session = get_session_trace()
    df = pd.read_sql_query(query, session.bind)
    session.close()
    df = df.replace({np.nan: None})
    df["attributes"] = df["attributes"].apply(lambda x: json.loads(x) if isinstance(x, str) else x)
    df_expanded = df.join(pd.json_normalize(df["attributes"]))
    trace_rowids = df_expanded[df_expanded["parent_id"].isna() & (df_expanded["project_id"] == str(project_id))][
        "trace_rowid"
    ].values
    return df[df["trace_rowid"].isin(trace_rowids)]


def query_trace_messages(
    duration_days: int,
) -> pd.DataFrame:
    start_time_offset_days = (datetime.now() - timedelta(days=duration_days)).isoformat()
    LOGGER.debug(f"Querying messages for since {start_time_offset_days}")

    query = (
        "SELECT m.span_id, m.input_content, m.output_content FROM span_messages m "
        "JOIN spans s ON m.span_id = s.span_id "
        f"WHERE s.start_time > '{start_time_offset_days}';"
    )
    session = get_session_trace()
    df = pd.read_sql_query(query, session.bind)
    session.close()

    return df


def query_root_trace_duration(project_id: UUID, duration_days: int) -> pd.DataFrame:
    start_time_offset_days = (datetime.now() - timedelta(days=duration_days)).isoformat()
    query = (
        "SELECT s.*, m.input_content, m.output_content FROM spans s "
        f"LEFT JOIN span_messages m ON m.span_id = s.span_id WHERE s.start_time > '{start_time_offset_days}' "
        "ORDER BY MAX(s.start_time) OVER (PARTITION BY s.trace_rowid) DESC, "
        "s.trace_rowid, s.start_time ASC;"
    )
    session = get_session_trace()
    df = pd.read_sql_query(query, session.bind)
    session.close()
    df = df.replace({np.nan: None})
    df["attributes"] = df["attributes"].apply(lambda x: json.loads(x) if isinstance(x, str) else x)
    df_expanded = df.join(pd.json_normalize(df["attributes"]))
    trace_rowids = df_expanded[df_expanded["parent_id"].isna() & (df_expanded["project_id"] == str(project_id))][
        "trace_rowid"
    ].values
    return df[(df["trace_rowid"].isin(trace_rowids)) & (df["parent_id"].isna())]


def query_trace_by_trace_id(trace_id: UUID) -> pd.DataFrame:
    query = (
        "SELECT s.*, m.input_content,m.output_content FROM spans s "
        f"LEFT JOIN span_messages m ON m.span_id = s.span_id WHERE s.trace_rowid = '{trace_id}';"
    )
    session = get_session_trace()
    df = pd.read_sql_query(query, session.bind)
    session.close()
    df = df.replace({np.nan: None})
    print(df.columns)
    print(df.head())
    return df
