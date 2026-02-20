import json
from datetime import datetime, timedelta
from uuid import UUID, uuid4

import numpy as np
from openinference.semconv.trace import OpenInferenceSpanKindValues
from opentelemetry.trace.status import StatusCode

from ada_backend.database.models import CallType, EnvType, SpanUsage
from ada_backend.database.setup_db import get_db_session
from ada_backend.database.trace_models import Span
from ada_backend.repositories.llm_models_repository import create_llm_model, delete_llm_model
from ada_backend.services.metrics.monitor_kpis_service import get_trace_cost_kpis


def _generate_span(
    organization_id: str | UUID,
    span_id: str | UUID,
    trace_rowid: str | UUID,
    parent_id: str | UUID,
    graph_runner_id: str | UUID,
    project_id: str | UUID,
    conversation_id: str | UUID,
    model_id: str | UUID,
    input_tokens: int,
    output_tokens: int,
):
    attrs = {
        "llm": {
            "provider": "anthropic",
            "model_name": "claude-haiku-4-5",
            "token_count": {
                "total": input_tokens + output_tokens,
                "prompt": input_tokens,
                "completion": output_tokens,
            },
            "invocation_parameters": '{"temperature": 1.0}',
        },
        "openinference": {"span": {"kind": "LLM"}},
        "conversation_id": str(conversation_id),
        "organization_id": str(organization_id),
        "organization_llm_providers": ["custom_llm"],
    }
    return {
        "parent_id": str(parent_id) if parent_id else None,
        "graph_runner_id": str(graph_runner_id) if graph_runner_id else None,
        "name": "Agentic reflexion",
        "span_kind": "LLM",
        "events": "[]",
        "cumulative_error_count": 0,
        "environment": "draft",
        "call_type": "sandbox",
        "tag_name": None,
        "component_instance_id": None,
        "trace_rowid": str(trace_rowid),
        "span_id": str(span_id),
        "project_id": str(project_id),
        "model_id": str(model_id) if model_id else None,
        "attributes": json.dumps(attrs),
        "cumulative_llm_token_count_prompt": input_tokens,
        "cumulative_llm_token_count_completion": output_tokens,
        "llm_token_count_prompt": input_tokens,
        "llm_token_count_completion": output_tokens,
    }


def _generate_span_usage(span_id: str | UUID, credits_input: float, credits_output: float):
    return {
        "span_id": str(span_id),
        "credits_input_token": credits_input,
        "credits_output_token": credits_output,
        "credits_per_call": None,
        "credits_per": None,
    }


def test_get_trace_cost_kpis():
    now = datetime.now()
    organization_id = uuid4()

    project1 = uuid4()
    conversation_id_project1 = uuid4()
    graph_runner_id_project1 = uuid4()
    trace_rowid_1_project1 = uuid4()
    trace_rowid_2_project1 = uuid4()
    span_id_1_project1 = uuid4()
    span_id_2_project1 = uuid4()
    parent_id_1_project1 = uuid4()
    parent_id_2_project1 = uuid4()
    credits_input_token_1_project1 = 34.0
    credits_output_token_1_project1 = 38.0
    credits_input_token_2_project1 = 80.0
    credits_output_token_2_project1 = 78.0

    project2 = uuid4()
    conversation_id_project2 = uuid4()
    graph_runner_id_project2 = uuid4()
    trace_rowid_1_project2 = uuid4()
    trace_rowid_2_project2 = uuid4()
    span_id_1_project2 = uuid4()
    span_id_2_project2 = uuid4()
    parent_id_1_project2 = uuid4()
    parent_id_2_project2 = uuid4()
    credits_input_token_1_project2 = 36.0
    credits_output_token_1_project2 = 22.0
    credits_input_token_2_project2 = 67.0
    credits_output_token_2_project2 = 65.0

    with get_db_session() as session:
        llm_model = create_llm_model(
            session,
            display_name="Test LLM Model",
            model_description="Fake LLM model for testing",
            model_capacity=None,
            model_provider="test_provider",
            model_name="test-model",
        )
        model_id = llm_model.id

        spans_project1 = [
            _generate_span(
                organization_id,
                span_id_1_project1,
                trace_rowid_1_project1,
                parent_id_1_project1,
                graph_runner_id_project1,
                project1,
                conversation_id_project1,
                model_id,
                0,
                0,
            ),
            _generate_span(
                organization_id,
                span_id_2_project1,
                trace_rowid_2_project1,
                parent_id_2_project1,
                graph_runner_id_project1,
                project1,
                conversation_id_project1,
                model_id,
                0,
                0,
            ),
        ]
        spans_project2 = [
            _generate_span(
                organization_id,
                span_id_1_project2,
                trace_rowid_1_project2,
                parent_id_1_project2,
                graph_runner_id_project2,
                project2,
                conversation_id_project2,
                model_id,
                0,
                0,
            ),
            _generate_span(
                organization_id,
                span_id_2_project2,
                trace_rowid_2_project2,
                parent_id_2_project2,
                graph_runner_id_project2,
                project2,
                conversation_id_project2,
                model_id,
                0,
                0,
            ),
        ]

        for span_data in spans_project1 + spans_project2:
            span = Span(
                trace_rowid=span_data["trace_rowid"],
                span_id=span_data["span_id"],
                parent_id=span_data["parent_id"],
                graph_runner_id=UUID(span_data["graph_runner_id"]) if span_data["graph_runner_id"] else None,
                name=span_data["name"],
                span_kind=OpenInferenceSpanKindValues(span_data["span_kind"]),
                start_time=now - timedelta(hours=12),
                end_time=now - timedelta(hours=12) + timedelta(seconds=1),
                attributes=json.loads(span_data["attributes"]),
                events=span_data["events"],
                status_code=StatusCode.OK,
                status_message="",
                cumulative_error_count=span_data["cumulative_error_count"],
                cumulative_llm_token_count_prompt=span_data["cumulative_llm_token_count_prompt"],
                cumulative_llm_token_count_completion=span_data["cumulative_llm_token_count_completion"],
                llm_token_count_prompt=span_data["llm_token_count_prompt"],
                llm_token_count_completion=span_data["llm_token_count_completion"],
                environment=EnvType(span_data["environment"]) if span_data["environment"] else None,
                call_type=CallType(span_data["call_type"]) if span_data["call_type"] else None,
                project_id=span_data["project_id"],
                tag_name=span_data["tag_name"],
                component_instance_id=UUID(span_data["component_instance_id"])
                if span_data["component_instance_id"]
                else None,
                model_id=UUID(span_data["model_id"]) if span_data["model_id"] else None,
            )
            session.add(span)

        session.commit()

        span_usages_project1 = [
            _generate_span_usage(span_id_1_project1, credits_input_token_1_project1, credits_output_token_1_project1),
            _generate_span_usage(span_id_2_project1, credits_input_token_2_project1, credits_output_token_2_project1),
        ]
        span_usages_project2 = [
            _generate_span_usage(span_id_1_project2, credits_input_token_1_project2, credits_output_token_1_project2),
            _generate_span_usage(span_id_2_project2, credits_input_token_2_project2, credits_output_token_2_project2),
        ]

        for su_data in span_usages_project1 + span_usages_project2:
            span_usage = SpanUsage(
                span_id=su_data["span_id"],
                credits_input_token=su_data["credits_input_token"],
                credits_output_token=su_data["credits_output_token"],
                credits_per_call=su_data["credits_per_call"],
                credits_per=su_data["credits_per"],
            )
            session.add(span_usage)

        session.commit()

        try:
            # Test project 1
            list_credits_project_1 = [
                credits_input_token_1_project1,
                credits_output_token_1_project1,
                credits_input_token_2_project1,
                credits_output_token_2_project1,
            ]
            sum_credits_project1 = np.sum(list_credits_project_1)
            result1 = get_trace_cost_kpis([project1], duration_days=1)
            assert result1.cost_per_call == sum_credits_project1 / 2
            assert result1.cost_per_conversation == sum_credits_project1

            # Test project 2
            list_credits_project_2 = [
                credits_input_token_1_project2,
                credits_output_token_1_project2,
                credits_input_token_2_project2,
                credits_output_token_2_project2,
            ]
            sum_credits_project2 = np.sum(list_credits_project_2)
            result2 = get_trace_cost_kpis([project2], duration_days=1)
            assert result2.cost_per_call == sum_credits_project2 / 2
            assert result2.cost_per_conversation == sum_credits_project2

            # Test both projects
            sum_credits_both = np.sum(list_credits_project_1 + list_credits_project_2)
            result_both = get_trace_cost_kpis([project1, project2], duration_days=1)
            assert result_both.cost_per_call == sum_credits_both / 4
            assert result_both.cost_per_conversation == sum_credits_both / 2

            # Test with call type
            result_both_with_call_type = get_trace_cost_kpis(
                [project1, project2], duration_days=1, call_type=CallType.SANDBOX
            )
            assert result_both_with_call_type.cost_per_call == sum_credits_both / 4
            assert result_both_with_call_type.cost_per_conversation == sum_credits_both / 2

            result_both_with_call_type = get_trace_cost_kpis(
                [project1, project2], duration_days=1, call_type=CallType.API
            )
            assert result_both_with_call_type.cost_per_call == 0
            assert result_both_with_call_type.cost_per_conversation == 0

        finally:
            # Cleanup: Remove test data we created
            # Delete span_usages first (due to foreign key constraint)
            span_ids_to_delete = [str(su_data["span_id"]) for su_data in span_usages_project1 + span_usages_project2]
            session.query(SpanUsage).filter(SpanUsage.span_id.in_(span_ids_to_delete)).delete(
                synchronize_session=False
            )

            # Delete spans
            trace_rowids_to_delete = [str(s["trace_rowid"]) for s in spans_project1 + spans_project2]
            session.query(Span).filter(Span.trace_rowid.in_(trace_rowids_to_delete)).delete(synchronize_session=False)

            delete_llm_model(session, model_id)

            session.commit()
