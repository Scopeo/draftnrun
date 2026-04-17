import json
from datetime import datetime, timedelta
from uuid import uuid4

from openinference.semconv.trace import OpenInferenceSpanKindValues
from opentelemetry.trace.status import StatusCode

from ada_backend.database.models import CallType, EnvType
from ada_backend.database.setup_db import get_db_session
from ada_backend.database.trace_models import Span, SpanMessage
from ada_backend.services.metrics.utils import query_root_trace_duration


def _create_root_span(project_id, trace_rowid, span_id, start_time):
    return Span(
        trace_rowid=str(trace_rowid),
        span_id=str(span_id),
        parent_id=None,
        graph_runner_id=None,
        name="Workflow",
        span_kind=OpenInferenceSpanKindValues.CHAIN,
        start_time=start_time,
        end_time=start_time + timedelta(seconds=1),
        attributes=json.dumps({"conversation_id": str(uuid4())}),
        events="[]",
        status_code=StatusCode.OK,
        status_message="",
        cumulative_error_count=0,
        cumulative_llm_token_count_prompt=0,
        cumulative_llm_token_count_completion=0,
        llm_token_count_prompt=0,
        llm_token_count_completion=0,
        environment=EnvType.DRAFT,
        call_type=CallType.SANDBOX,
        project_id=str(project_id),
        tag_name=None,
        component_instance_id=None,
        model_id=None,
    )


def _create_span_message(span_id, input_content, output_content="[]"):
    return SpanMessage(
        span_id=str(span_id),
        input_content=input_content,
        output_content=output_content,
    )


def test_search_traces_by_keyword():
    now = datetime.now()
    project_id = uuid4()

    trace1_id = uuid4()
    span1_id = uuid4()

    trace2_id = uuid4()
    span2_id = uuid4()

    trace3_id = uuid4()
    span3_id = uuid4()

    with get_db_session() as session:
        span1 = _create_root_span(project_id, trace1_id, span1_id, now - timedelta(hours=1))
        span2 = _create_root_span(project_id, trace2_id, span2_id, now - timedelta(hours=2))
        span3 = _create_root_span(project_id, trace3_id, span3_id, now - timedelta(hours=3))
        session.add_all([span1, span2, span3])
        session.commit()

        msg1 = _create_span_message(
            span1_id,
            json.dumps([{"messages": [{"role": "user", "content": "Hello world"}]}]),
        )
        msg2 = _create_span_message(
            span2_id,
            json.dumps([{"messages": [{"role": "user", "content": "Goodbye moon"}]}]),
        )
        msg3 = _create_span_message(
            span3_id,
            json.dumps([{"messages": [{"role": "user", "content": "Hello again"}]}]),
        )
        session.add_all([msg1, msg2, msg3])
        session.commit()

        try:
            rows_all, _ = query_root_trace_duration(project_id, duration_days=1)
            assert len(rows_all) == 3

            rows_hello, total_pages = query_root_trace_duration(project_id, duration_days=1, search="Hello")
            assert len(rows_hello) == 2
            assert total_pages == 1
            trace_ids = {row["trace_rowid"] for row in rows_hello}
            assert str(trace1_id) in trace_ids
            assert str(trace3_id) in trace_ids

            rows_goodbye, _ = query_root_trace_duration(project_id, duration_days=1, search="Goodbye")
            assert len(rows_goodbye) == 1
            assert rows_goodbye[0]["trace_rowid"] == str(trace2_id)

            rows_none, _ = query_root_trace_duration(project_id, duration_days=1, search="nonexistent_xyz")
            assert len(rows_none) == 0

            rows_case, _ = query_root_trace_duration(project_id, duration_days=1, search="hello")
            assert len(rows_case) == 2

        finally:
            session.query(SpanMessage).filter(
                SpanMessage.span_id.in_([str(span1_id), str(span2_id), str(span3_id)])
            ).delete(synchronize_session=False)
            session.query(Span).filter(
                Span.trace_rowid.in_([str(trace1_id), str(trace2_id), str(trace3_id)])
            ).delete(synchronize_session=False)
            session.commit()


def test_search_traces_with_special_characters():
    now = datetime.now()
    project_id = uuid4()

    trace_utf8_id, span_utf8_id = uuid4(), uuid4()
    trace_escaped_id, span_escaped_id = uuid4(), uuid4()
    trace_plain_id, span_plain_id = uuid4(), uuid4()

    with get_db_session() as session:
        span_utf8 = _create_root_span(project_id, trace_utf8_id, span_utf8_id, now - timedelta(hours=1))
        span_escaped = _create_root_span(project_id, trace_escaped_id, span_escaped_id, now - timedelta(hours=2))
        span_plain = _create_root_span(project_id, trace_plain_id, span_plain_id, now - timedelta(hours=3))
        session.add_all([span_utf8, span_escaped, span_plain])
        session.commit()

        msg_utf8 = _create_span_message(
            span_utf8_id,
            json.dumps([{"messages": [{"role": "user", "content": "Bonjour résumé"}]}], ensure_ascii=False),
        )
        msg_escaped = _create_span_message(
            span_escaped_id,
            json.dumps([{"messages": [{"role": "user", "content": "Bonjour résumé"}]}], ensure_ascii=True),
        )
        msg_plain = _create_span_message(
            span_plain_id,
            json.dumps([{"messages": [{"role": "user", "content": "Hello world 100% done"}]}]),
        )
        session.add_all([msg_utf8, msg_escaped, msg_plain])
        session.commit()

        all_span_ids = [str(span_utf8_id), str(span_escaped_id), str(span_plain_id)]
        all_trace_ids = [str(trace_utf8_id), str(trace_escaped_id), str(trace_plain_id)]

        try:
            rows_accent, _ = query_root_trace_duration(project_id, duration_days=1, search="résumé")
            assert len(rows_accent) == 2
            trace_ids = {row["trace_rowid"] for row in rows_accent}
            assert str(trace_utf8_id) in trace_ids
            assert str(trace_escaped_id) in trace_ids

            rows_percent, _ = query_root_trace_duration(project_id, duration_days=1, search="100%")
            assert len(rows_percent) == 1
            assert rows_percent[0]["trace_rowid"] == str(trace_plain_id)

            rows_bare_percent, _ = query_root_trace_duration(project_id, duration_days=1, search="%")
            assert len(rows_bare_percent) == 1
            assert rows_bare_percent[0]["trace_rowid"] == str(trace_plain_id)

        finally:
            session.query(SpanMessage).filter(
                SpanMessage.span_id.in_(all_span_ids)
            ).delete(synchronize_session=False)
            session.query(Span).filter(
                Span.trace_rowid.in_(all_trace_ids)
            ).delete(synchronize_session=False)
            session.commit()


def test_filter_traces_by_date_range():
    now = datetime.now()
    project_id = uuid4()

    trace1_id, span1_id = uuid4(), uuid4()
    trace2_id, span2_id = uuid4(), uuid4()
    trace3_id, span3_id = uuid4(), uuid4()

    with get_db_session() as session:
        span1 = _create_root_span(project_id, trace1_id, span1_id, now - timedelta(hours=1))
        span2 = _create_root_span(project_id, trace2_id, span2_id, now - timedelta(hours=5))
        span3 = _create_root_span(project_id, trace3_id, span3_id, now - timedelta(hours=10))
        session.add_all([span1, span2, span3])
        session.commit()

        msg1 = _create_span_message(span1_id, json.dumps([{"messages": [{"role": "user", "content": "a"}]}]))
        msg2 = _create_span_message(span2_id, json.dumps([{"messages": [{"role": "user", "content": "b"}]}]))
        msg3 = _create_span_message(span3_id, json.dumps([{"messages": [{"role": "user", "content": "c"}]}]))
        session.add_all([msg1, msg2, msg3])
        session.commit()

        try:
            rows, _ = query_root_trace_duration(
                project_id,
                start_time=now - timedelta(hours=6),
                end_time=now,
            )
            assert len(rows) == 2
            trace_ids = {row["trace_rowid"] for row in rows}
            assert str(trace1_id) in trace_ids
            assert str(trace2_id) in trace_ids

            rows_start_only, _ = query_root_trace_duration(
                project_id,
                start_time=now - timedelta(hours=2),
            )
            assert len(rows_start_only) == 1
            assert rows_start_only[0]["trace_rowid"] == str(trace1_id)

            rows_end_only, _ = query_root_trace_duration(
                project_id,
                end_time=now - timedelta(hours=4),
            )
            assert len(rows_end_only) == 2
            trace_ids_end = {row["trace_rowid"] for row in rows_end_only}
            assert str(trace2_id) in trace_ids_end
            assert str(trace3_id) in trace_ids_end

            rows_range_takes_precedence, _ = query_root_trace_duration(
                project_id,
                duration_days=1,
                start_time=now - timedelta(hours=2),
                end_time=now,
            )
            assert len(rows_range_takes_precedence) == 1
            assert rows_range_takes_precedence[0]["trace_rowid"] == str(trace1_id)

        finally:
            span_ids = [str(span1_id), str(span2_id), str(span3_id)]
            trace_ids_cleanup = [str(trace1_id), str(trace2_id), str(trace3_id)]
            session.query(SpanMessage).filter(SpanMessage.span_id.in_(span_ids)).delete(synchronize_session=False)
            session.query(Span).filter(Span.trace_rowid.in_(trace_ids_cleanup)).delete(synchronize_session=False)
            session.commit()
