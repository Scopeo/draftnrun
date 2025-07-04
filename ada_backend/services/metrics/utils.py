from datetime import timedelta, datetime
import json
from uuid import UUID

import numpy as np
import pandas as pd

from engine.trace.sql_exporter import get_session_trace


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
