import json
from uuid import uuid4

import pandas as pd
import pytest

from ada_backend.services import trace_service as ts
from ada_backend.schemas.trace_schema import TraceSpan


def test_get_span_trace_service_success(monkeypatch):
    user_id = uuid4()
    trace_id = uuid4()

    # build a fake dataframe expected by build_span_trees
    df = pd.DataFrame(
        [
            {
                "trace_rowid": str(trace_id),
                "span_id": "s1",
                "parent_id": None,
                "span_kind": "LLM",
                "name": "root",
                "start_time": None,
                "end_time": None,
                "input_content": json.dumps([]),
                "output_content": json.dumps([]),
                "events": json.dumps([]),
                "attributes": {},
                "status_code": 0,
                "cumulative_llm_token_count_prompt": 0,
                "cumulative_llm_token_count_completion": 0,
            }
        ]
    )

    # mock query_trace_by_trace_id to return df
    monkeypatch.setattr(ts, "query_trace_by_trace_id", lambda tid: df)
    called = {}

    def fake_track(uid, tid):
        called["tracked"] = (uid, tid)

    monkeypatch.setattr(ts, "track_span_observability_loaded", fake_track)

    # call service
    span = ts.get_span_trace_service(user_id, trace_id)

    assert isinstance(span, TraceSpan)
    assert called["tracked"] == (user_id, trace_id)


def test_get_span_trace_service_no_spans(monkeypatch):
    user_id = uuid4()
    trace_id = uuid4()

    # empty df
    df = pd.DataFrame([])
    monkeypatch.setattr(ts, "query_trace_by_trace_id", lambda tid: df)

    with pytest.raises(ValueError) as exc:
        ts.get_span_trace_service(user_id, trace_id)
    assert f"No spans found for trace_id {trace_id}" in str(exc.value)
