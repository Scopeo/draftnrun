from datetime import timedelta, datetime
from uuid import UUID
import logging
import json

import numpy as np
import pandas as pd

from engine.trace.sql_exporter import get_session_trace

LOGGER = logging.getLogger(__name__)


def query_trace_duration(project_id: UUID, duration_days: int) -> pd.DataFrame:
    start_time_offset_days = (datetime.now() - timedelta(days=duration_days)).isoformat()

    query = f"""
    WITH root_spans AS (
        SELECT trace_rowid
        FROM spans
        WHERE parent_id IS NULL
        AND project_id = '{project_id}'
        AND start_time > '{start_time_offset_days}'
    )
    SELECT s.*
    FROM spans s
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
    df = df.replace({np.nan: None})
    return df


def query_root_trace_duration(project_id: UUID, duration_days: int) -> pd.DataFrame:
    start_time_offset_days = (datetime.now() - timedelta(days=duration_days)).isoformat()

    query = f"""
    SELECT s.*, m.input_content, m.output_content
    FROM spans s
    LEFT JOIN span_messages m ON m.span_id = s.span_id
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
        "SELECT s.*, m.input_content,m.output_content FROM spans s "
        f"LEFT JOIN span_messages m ON m.span_id = s.span_id WHERE s.trace_rowid = '{trace_id}';"
    )
    session = get_session_trace()
    df = pd.read_sql_query(query, session.bind)
    session.close()
    df["attributes"] = df["attributes"].apply(lambda x: json.loads(x) if isinstance(x, str) else x)
    df = df.replace({np.nan: None})
    return df
