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
        "SELECT m1.span_id, m1.content AS input_content, m2.content AS output_content "
        "FROM messages m1 JOIN messages m2 ON m1.span_id = m2.span_id "
        "JOIN spans s ON m1.span_id = s.span_id "
        "WHERE m1.direction = 'input' AND m2.direction = 'output' "
        f"AND s.start_time > '{start_time_offset_days}';"
    )
    session = get_session_trace()
    df = pd.read_sql_query(query, session.bind)
    session.close()
    df = df.replace({np.nan: None})

    return df
