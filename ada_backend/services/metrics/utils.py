from datetime import timedelta, datetime
import json
from uuid import UUID
from pathlib import Path

import numpy as np
import pandas as pd
import sqlite3

from engine.trace.models import TRACES_DB_URL


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
    db_path = get_trace_db_path()
    conn = sqlite3.connect(db_path)
    df = pd.read_sql_query(query, conn)
    conn.close()
    df = df.replace({np.nan: None})
    df["attributes"] = df["attributes"].apply(lambda x: json.loads(x) if isinstance(x, str) else x)
    df_expanded = df.join(pd.json_normalize(df["attributes"]))
    trace_rowids = df_expanded[df_expanded["parent_id"].isna() & (df_expanded["project_id"] == str(project_id))][
        "trace_rowid"
    ].values
    return df[df["trace_rowid"].isin(trace_rowids)]
