from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from openinference.semconv.trace import OpenInferenceSpanKindValues
from opentelemetry.trace.status import StatusCode

from ada_backend.database.models import EnvType, Project, WorkflowProject
from ada_backend.database.setup_db import get_db_session
from ada_backend.database.trace_models import Span
from ada_backend.repositories.llm_models_repository import create_llm_model, delete_llm_model
from ada_backend.services.metrics.monitor_kpis_service import get_org_token_usage


def _span(
    *,
    span_id: UUID,
    trace_rowid: UUID,
    project_id: UUID,
    start_time: datetime,
    input_tokens: int | None,
    output_tokens: int | None,
    model_id: UUID | None,
) -> Span:
    return Span(
        trace_rowid=str(trace_rowid),
        span_id=str(span_id),
        parent_id=None,
        graph_runner_id=None,
        name="LLM",
        span_kind=OpenInferenceSpanKindValues.LLM,
        start_time=start_time,
        end_time=start_time + timedelta(seconds=1),
        attributes={},
        events="[]",
        status_code=StatusCode.OK,
        status_message="",
        cumulative_error_count=0,
        cumulative_llm_token_count_prompt=input_tokens or 0,
        cumulative_llm_token_count_completion=output_tokens or 0,
        llm_token_count_prompt=input_tokens,
        llm_token_count_completion=output_tokens,
        environment=EnvType.DRAFT,
        call_type=None,
        project_id=str(project_id),
        tag_name=None,
        component_instance_id=None,
        model_id=model_id,
    )


def test_get_org_token_usage_aggregates_monthly_tokens_by_model():
    organization_id = uuid4()
    other_organization_id = uuid4()
    project_id = uuid4()
    project_id_2 = uuid4()
    other_org_project_id = uuid4()
    month_start = datetime(2026, 7, 1, tzinfo=timezone.utc)
    previous_month = datetime(2026, 6, 30, 23, 59, tzinfo=timezone.utc)

    with get_db_session() as session:
        llm_model = create_llm_model(
            session,
            display_name="Test Model",
            model_description="Fake LLM model for org token usage tests",
            model_capacity=None,
            model_provider="test-provider",
            model_name="test-model",
        )
        model_id = llm_model.id
        projects = [
            WorkflowProject(id=project_id, name=f"token-usage-{project_id}", organization_id=organization_id),
            WorkflowProject(id=project_id_2, name=f"token-usage-{project_id_2}", organization_id=organization_id),
            WorkflowProject(
                id=other_org_project_id,
                name=f"token-usage-{other_org_project_id}",
                organization_id=other_organization_id,
            ),
        ]
        session.add_all(projects)
        spans = [
            _span(
                span_id=uuid4(),
                trace_rowid=uuid4(),
                project_id=project_id,
                start_time=month_start + timedelta(days=1),
                input_tokens=10,
                output_tokens=3,
                model_id=model_id,
            ),
            _span(
                span_id=uuid4(),
                trace_rowid=uuid4(),
                project_id=project_id_2,
                start_time=month_start + timedelta(days=2),
                input_tokens=5,
                output_tokens=7,
                model_id=model_id,
            ),
            _span(
                span_id=uuid4(),
                trace_rowid=uuid4(),
                project_id=project_id,
                start_time=month_start + timedelta(days=3),
                input_tokens=2,
                output_tokens=4,
                model_id=None,
            ),
            _span(
                span_id=uuid4(),
                trace_rowid=uuid4(),
                project_id=project_id,
                start_time=previous_month,
                input_tokens=100,
                output_tokens=100,
                model_id=model_id,
            ),
            _span(
                span_id=uuid4(),
                trace_rowid=uuid4(),
                project_id=other_org_project_id,
                start_time=month_start + timedelta(days=1),
                input_tokens=100,
                output_tokens=100,
                model_id=model_id,
            ),
        ]
        session.add_all(spans)
        session.commit()

        try:
            result = get_org_token_usage(organization_id=organization_id, years=[2026], months=[7])

            assert result.totals.input_tokens == 17
            assert result.totals.output_tokens == 14
            assert result.totals.total_tokens == 31
            assert len(result.periods) == 1

            july_period = result.periods[0]
            assert july_period.year == 2026
            assert july_period.month == 7
            assert july_period.input_tokens == 17
            assert july_period.output_tokens == 14
            assert july_period.total_tokens == 31
            assert len(july_period.by_model) == 2

            model_row = next(row for row in july_period.by_model if row.model_id == model_id)
            assert model_row.provider == "test-provider"
            assert model_row.model_name == "test-model"
            assert model_row.display_name == "Test Model"
            assert model_row.input_tokens == 15
            assert model_row.output_tokens == 10
            assert model_row.total_tokens == 25

            null_model_row = next(row for row in july_period.by_model if row.model_id is None)
            assert null_model_row.input_tokens == 2
            assert null_model_row.output_tokens == 4
            assert null_model_row.total_tokens == 6

            without_model_breakdown = get_org_token_usage(
                organization_id=organization_id,
                years=[2026],
                months=[7],
                by_model=False,
            )
            assert without_model_breakdown.totals.input_tokens == 17
            assert without_model_breakdown.totals.output_tokens == 14
            assert without_model_breakdown.periods[0].by_model == []

            all_2026_months = get_org_token_usage(organization_id=organization_id, years=[2026], months=None)
            assert [(period.year, period.month) for period in all_2026_months.periods] == [(2026, 7), (2026, 6)]
            assert all_2026_months.totals.input_tokens == 117
            assert all_2026_months.totals.output_tokens == 114
            assert all_2026_months.totals.total_tokens == 231

            empty_month = get_org_token_usage(organization_id=organization_id, years=[2026], months=[8])
            assert empty_month.periods == []
            assert empty_month.totals.input_tokens == 0
            assert empty_month.totals.output_tokens == 0
            assert empty_month.totals.total_tokens == 0
        finally:
            span_ids = [span.span_id for span in spans]
            project_ids = [project.id for project in projects]
            session.query(Span).filter(Span.span_id.in_(span_ids)).delete(synchronize_session=False)
            session.query(WorkflowProject).filter(WorkflowProject.id.in_([project.id for project in projects])).delete(
                synchronize_session=False
            )
            session.query(Project).filter(Project.id.in_(project_ids)).delete(synchronize_session=False)
            delete_llm_model(session, model_id)
            session.commit()
