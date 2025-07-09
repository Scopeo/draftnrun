from datetime import timedelta, datetime
import json
from pathlib import Path
from uuid import UUID

import numpy as np
import pandas as pd

from engine.trace.sql_exporter import get_session_trace
from engine.trace.models import TRACES_DB_URL
from engine.trace.trace_manager import USER_AGENT_TRACE_TYPE


def get_trace_db_path() -> Path:
    path_name = TRACES_DB_URL.split("///")[1]
    db_path = Path(path_name).expanduser()
    if db_path.exists():
        return db_path
    else:
        raise FileNotFoundError("Database file not found.")


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
    # Find root agent execution spans: user-agent traces with is_root_agent_execution=True
    # Build filter conditions, handling missing columns gracefully
    conditions = df_expanded["project_id"] == str(project_id)

    if "trace.type" in df_expanded.columns:
        conditions = conditions & (df_expanded["trace.type"] == USER_AGENT_TRACE_TYPE)
    else:
        # If no trace.type column, no user-agent spans exist
        return pd.DataFrame()

    if "is_root_agent_execution" in df_expanded.columns:
        conditions = conditions & df_expanded["is_root_agent_execution"]
    else:
        # If no root flag column, no root spans exist
        return pd.DataFrame()

    trace_rowids = df_expanded[conditions]["trace_rowid"].values
    return df[df["trace_rowid"].isin(trace_rowids)]
