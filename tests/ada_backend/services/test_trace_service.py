import json
from uuid import uuid4

import pandas as pd
import pytest

from ada_backend.services import trace_service
from ada_backend.schemas.trace_schema import TraceSpan
from ada_backend.database.models import EnvType, CallType
from engine.trace import sql_exporter


def test_get_token_usage(monkeypatch):
    org_id = uuid4()

    # Case 1: no usage row -> should return total_tokens = 0
    class EmptySession:
        def query(self, *args, **kwargs):
            class Q:
                def filter_by(self, **f):
                    class F:
                        def first(self):
                            return None

                    return F()

            return Q()

        def close(self):
            pass

    monkeypatch.setattr(sql_exporter, "get_session_trace", lambda: EmptySession())

    res = trace_service.get_token_usage(org_id)
    assert res.organization_id == str(org_id)
    assert res.total_tokens == 0

    # Case 2: existing usage row
    class Usage:
        def __init__(self, organization_id, total_tokens):
            self.organization_id = organization_id
            self.total_tokens = total_tokens

    class SessionWithUsage:
        def __init__(self, usage):
            self._usage = usage

        def query(self, *args, **kwargs):
            class Q:
                def __init__(self, usage):
                    self._usage = usage

                def filter_by(self, **f):
                    class F:
                        def __init__(self, usage):
                            self._usage = usage

                        def first(self):
                            return self._usage

                    return F(self._usage)

            return Q(self._usage)

        def close(self):
            pass

    usage = Usage(str(org_id), 12345)
    monkeypatch.setattr(sql_exporter, "get_session_trace", lambda: SessionWithUsage(usage))

    # Mock get_organization_token_usage where it's imported in the service module
    monkeypatch.setattr("ada_backend.services.trace_service.get_organization_token_usage", lambda org_id: usage)

    res2 = trace_service.get_token_usage(org_id)
    assert res2.organization_id == usage.organization_id
    assert res2.total_tokens == usage.total_tokens


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
                "status_code": "OK",
                "cumulative_llm_token_count_prompt": 0,
                "cumulative_llm_token_count_completion": 0,
            }
        ]
    )

    # mock query_trace_by_trace_id to return df
    monkeypatch.setattr(trace_service, "query_trace_by_trace_id", lambda tid: df)
    called = {}

    def fake_track(uid, tid):
        called["tracked"] = (uid, tid)

    monkeypatch.setattr(trace_service, "track_span_observability_loaded", fake_track)

    # call service
    span = trace_service.get_span_trace_service(user_id, trace_id)

    assert isinstance(span, TraceSpan)
    assert called["tracked"] == (user_id, trace_id)


def test_get_span_trace_service_no_spans(monkeypatch):
    user_id = uuid4()
    trace_id = uuid4()

    # empty df
    df = pd.DataFrame([])
    monkeypatch.setattr(trace_service, "query_trace_by_trace_id", lambda tid: df)

    with pytest.raises(ValueError) as exc:
        trace_service.get_span_trace_service(user_id, trace_id)
    assert f"No spans found for trace_id {trace_id}" in str(exc.value)


def make_row(trace_id, span_id, name, span_kind, environment=None, call_type=None):
    return {
        "trace_rowid": str(trace_id),
        "span_id": str(span_id),
        "parent_id": None,
        "name": name,
        "span_kind": span_kind,
        "start_time": None,
        "end_time": None,
        # build_root_spans uses get_attributes_with_messages which expects these fields
        "input_content": json.dumps([]),
        "output_content": json.dumps([]),
        "attributes": {},
        "events": json.dumps([]),
        "status_code": "OK",
        "cumulative_llm_token_count_prompt": 0,
        "cumulative_llm_token_count_completion": 0,
        "llm_token_count_prompt": None,
        "llm_token_count_completion": None,
        "environment": environment.value if environment is not None else None,
        "call_type": call_type.value if call_type is not None else None,
    }


def test_get_root_traces_by_project_no_filter(monkeypatch):
    project_id = uuid4()
    user_id = uuid4()

    # create two root spans
    r1 = make_row(uuid4(), uuid4(), "root1", "LLM")
    r2 = make_row(uuid4(), uuid4(), "root2", "RETRIEVER")

    df = pd.DataFrame([r1, r2])

    monkeypatch.setattr(
        trace_service,
        "query_root_trace_duration",
        lambda proj_id, duration: df,
    )

    paginated_roots_response = trace_service.get_root_traces_by_project(
        user_id=user_id, project_id=project_id, duration=7
    )
    roots = paginated_roots_response.traces

    assert len(roots) == 2
    names = {r.name for r in roots}
    assert names == {"root1", "root2"}


def test_get_root_traces_by_project_with_filters(monkeypatch):
    project_id = uuid4()
    user_id = uuid4()

    # create three root spans with different envs and call types
    r1 = make_row(uuid4(), uuid4(), "a", "LLM", environment=EnvType.PRODUCTION, call_type=CallType.API)
    r2 = make_row(uuid4(), uuid4(), "b", "LLM", environment=EnvType.DRAFT, call_type=CallType.SANDBOX)
    r3 = make_row(uuid4(), uuid4(), "c", "LLM", environment=EnvType.PRODUCTION, call_type=CallType.SANDBOX)

    df = pd.DataFrame([r1, r2, r3])

    monkeypatch.setattr(
        trace_service,
        "query_root_trace_duration",
        lambda proj_id, duration: df,
    )

    paginated_roots_env_response = trace_service.get_root_traces_by_project(
        user_id=user_id, project_id=project_id, duration=7, environment=EnvType.PRODUCTION
    )
    roots_env = paginated_roots_env_response.traces
    assert len(roots_env) == 2
    assert {r.name for r in roots_env} == {"a", "c"}

    paginated_roots_call_response = trace_service.get_root_traces_by_project(
        user_id=user_id, project_id=project_id, duration=7, call_type=CallType.SANDBOX
    )
    roots_call = paginated_roots_call_response.traces
    assert len(roots_call) == 2
    assert {r.name for r in roots_call} == {"b", "c"}
