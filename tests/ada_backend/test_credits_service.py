from datetime import datetime
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ada_backend.context import RequestContext, set_request_context
from ada_backend.database import models as db
from ada_backend.database.models import SpanUsage, Usage
from ada_backend.database.seed.utils import COMPONENT_UUIDS, COMPONENT_VERSION_UUIDS
from ada_backend.database.setup_db import SessionLocal, get_db_session
from ada_backend.database.trace_models import Span
from ada_backend.repositories.credits_repository import (
    create_component_version_cost,
    create_llm_cost,
    create_organization_limit,
    delete_component_version_cost,
    delete_organization_limit,
    upsert_component_version_cost,
)
from ada_backend.repositories.llm_models_repository import create_llm_model
from ada_backend.repositories.organization_repository import delete_organization_secret, upsert_organization_secret
from ada_backend.schemas.parameter_schema import PipelineParameterSchema
from ada_backend.schemas.pipeline.base import ComponentInstanceSchema
from ada_backend.schemas.pipeline.graph_schema import EdgeSchema, GraphUpdateSchema
from ada_backend.services.agent_runner_service import run_env_agent, setup_tracing_context
from ada_backend.services.credits_service import (
    create_organization_limit_service,
    delete_component_version_cost_service,
    delete_organization_limit_service,
    get_all_organization_limits_and_usage_service,
    update_organization_limit_service,
    upsert_component_version_cost_service,
)
from ada_backend.services.errors import OrganizationLimitNotFound
from ada_backend.services.graph.update_graph_service import update_graph_service
from ada_backend.services.llm_models_service import delete_llm_model_service
from ada_backend.services.project_service import delete_project_service
from engine.trace.trace_context import set_trace_manager
from engine.trace.trace_manager import TraceManager
from tests.ada_backend.test_utils import create_project_and_graph_runner

ORGANIZATION_ID = UUID("37b7d67f-8f29-4fce-8085-19dea582f605")  # umbrella organization
COMPONENT_VERSION_ID = str(COMPONENT_VERSION_UUIDS["llm_call"])


@pytest.fixture
def db_session():
    """Provide a database session for testing."""
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def ensure_component_version(db_session):
    """Ensure component version exists, create if needed. Returns the component_version_id."""
    component_version_id = UUID(COMPONENT_VERSION_ID)

    component_version = db_session.query(db.ComponentVersion).filter_by(id=component_version_id).first()
    if not component_version:
        component = db.Component(
            id=uuid4(),
            name="Test Component",
            description="Test",
        )
        db_session.add(component)
        db_session.commit()

        component_version = db.ComponentVersion(
            id=component_version_id,
            component_id=component.id,
            release_stage=db.ReleaseStage.DRAFT,
        )
        db_session.add(component_version)
        db_session.commit()

    yield component_version_id


def create_component_version_cost_in_db(session, component_version_id: UUID, **kwargs):
    """Helper to create a component version cost in the database using repository function."""
    return create_component_version_cost(
        session,
        component_version_id,
        credits_per_call=kwargs.get("credits_per_call"),
        credits_per=kwargs.get("credits_per"),
    )


def create_organization_limit_in_db(session, organization_id: UUID, limit: float):
    """Helper to create an organization limit in the database using repository function."""
    return create_organization_limit(session, organization_id, limit)


def test_get_all_organization_limits_and_usage(db_session):
    """Test getting all organization limits with usage."""
    org_id_2 = uuid4()

    existing_limits = (
        db_session.query(db.OrganizationLimit)
        .filter(db.OrganizationLimit.organization_id.in_([ORGANIZATION_ID, org_id_2]))
        .all()
    )
    for limit in existing_limits:
        delete_organization_limit(db_session, limit.id, limit.organization_id)

    limit_1 = create_organization_limit_in_db(db_session, ORGANIZATION_ID, 1000.0)
    limit_2 = create_organization_limit_in_db(db_session, org_id_2, 2000.0)

    result = get_all_organization_limits_and_usage_service(db_session, month=12, year=2025)

    assert isinstance(result, list)
    assert len(result) >= 2

    for item in result:
        assert hasattr(item, "organization_id")
        assert hasattr(item, "limit")
        assert hasattr(item, "total_credits_used")

    delete_organization_limit(db_session, limit_1.id, limit_1.organization_id)
    delete_organization_limit(db_session, limit_2.id, limit_2.organization_id)


def test_create_organization_limit_success(db_session):
    """Test creating an organization limit."""

    existing_limits = (
        db_session.query(db.OrganizationLimit).filter(db.OrganizationLimit.organization_id == ORGANIZATION_ID).all()
    )
    for limit in existing_limits:
        delete_organization_limit(db_session, limit.id, limit.organization_id)

    result = create_organization_limit_service(db_session, ORGANIZATION_ID, 5000.0)

    assert result.organization_id == ORGANIZATION_ID
    assert result.limit == 5000.0
    assert result.id is not None
    assert result.created_at is not None
    assert result.updated_at is not None

    limit_id = result.id
    delete_organization_limit(db_session, limit_id, ORGANIZATION_ID)


def test_update_organization_limit_success(db_session):
    """Test updating an organization limit."""

    existing_limits = (
        db_session.query(db.OrganizationLimit).filter(db.OrganizationLimit.organization_id == ORGANIZATION_ID).all()
    )
    for limit in existing_limits:
        delete_organization_limit(db_session, limit.id, limit.organization_id)

    org_limit = create_organization_limit_in_db(db_session, ORGANIZATION_ID, 3000.0)
    limit_id = org_limit.id

    new_limit = 6000.0
    result = update_organization_limit_service(
        db_session, id=limit_id, organization_id=ORGANIZATION_ID, limit=new_limit
    )

    assert result.id == limit_id
    assert result.organization_id == ORGANIZATION_ID
    assert result.limit == new_limit

    delete_organization_limit(db_session, limit_id, ORGANIZATION_ID)


def test_update_organization_limit_not_found(db_session):
    """Test updating a non-existent organization limit."""
    fake_limit_id = uuid4()
    new_limit = 6000.0

    with pytest.raises(OrganizationLimitNotFound):
        update_organization_limit_service(
            db_session, id=fake_limit_id, organization_id=ORGANIZATION_ID, limit=new_limit
        )


def test_delete_organization_limit_success(db_session):
    """Test deleting an organization limit."""

    existing_limits = (
        db_session.query(db.OrganizationLimit).filter(db.OrganizationLimit.organization_id == ORGANIZATION_ID).all()
    )
    for limit in existing_limits:
        delete_organization_limit(db_session, limit.id, limit.organization_id)

    org_limit = create_organization_limit_in_db(db_session, ORGANIZATION_ID, 4000.0)
    limit_id = org_limit.id

    delete_organization_limit_service(db_session, limit_id, ORGANIZATION_ID)

    all_limits = db_session.query(db.OrganizationLimit).all()
    limit_ids = [limit.id for limit in all_limits]
    assert limit_id not in limit_ids


def test_create_organization_limit_duplicate(db_session):
    """Test creating a duplicate organization limit (same org) should fail."""
    existing_limits = (
        db_session.query(db.OrganizationLimit).filter(db.OrganizationLimit.organization_id == ORGANIZATION_ID).all()
    )
    for limit in existing_limits:
        delete_organization_limit(db_session, limit.id, limit.organization_id)

    org_limit = create_organization_limit_in_db(db_session, ORGANIZATION_ID, 5000.0)

    with pytest.raises(IntegrityError):
        create_organization_limit_service(db_session, ORGANIZATION_ID, 6000.0)
    db_session.rollback()  # Rollback after IntegrityError to keep session clean

    delete_organization_limit(db_session, org_limit.id, ORGANIZATION_ID)


def test_create_organization_limit_missing_fields(db_session):
    """Test creating an organization limit with default limit value."""

    existing_limits = (
        db_session.query(db.OrganizationLimit).filter(db.OrganizationLimit.organization_id == ORGANIZATION_ID).all()
    )
    for limit in existing_limits:
        delete_organization_limit(db_session, limit.id, limit.organization_id)

    result = create_organization_limit_service(db_session, ORGANIZATION_ID, 0.0)

    assert result.limit == 0.0

    limit_id = result.id
    delete_organization_limit(db_session, limit_id, ORGANIZATION_ID)


def test_update_organization_limit_same_value(db_session):
    """Test updating an organization limit with the same value."""

    existing_limits = (
        db_session.query(db.OrganizationLimit).filter(db.OrganizationLimit.organization_id == ORGANIZATION_ID).all()
    )
    for limit in existing_limits:
        delete_organization_limit(db_session, limit.id, limit.organization_id)

    org_limit = create_organization_limit_in_db(db_session, ORGANIZATION_ID, 5000.0)
    limit_id = org_limit.id

    result = update_organization_limit_service(db_session, id=limit_id, organization_id=ORGANIZATION_ID, limit=5000.0)

    assert result.limit == 5000.0

    delete_organization_limit(db_session, limit_id, ORGANIZATION_ID)


def test_update_organization_limit_zero_limit(db_session):
    """Test updating an organization limit with zero limit."""

    existing_limits = (
        db_session.query(db.OrganizationLimit).filter(db.OrganizationLimit.organization_id == ORGANIZATION_ID).all()
    )
    for limit in existing_limits:
        delete_organization_limit(db_session, limit.id, limit.organization_id)

    org_limit = create_organization_limit_in_db(db_session, ORGANIZATION_ID, 1000.0)
    limit_id = org_limit.id

    result = update_organization_limit_service(db_session, id=limit_id, organization_id=ORGANIZATION_ID, limit=0.0)

    assert result.limit == 0.0

    delete_organization_limit(db_session, limit_id, ORGANIZATION_ID)


def test_get_all_organization_limits_and_usage_with_filters(db_session):
    """Test getting all organization limits with usage."""

    existing_limits = (
        db_session.query(db.OrganizationLimit).filter(db.OrganizationLimit.organization_id == ORGANIZATION_ID).all()
    )
    for limit in existing_limits:
        delete_organization_limit(db_session, limit.id, limit.organization_id)

    limit_1 = create_organization_limit_in_db(db_session, ORGANIZATION_ID, 1000.0)
    limit_2 = create_organization_limit_in_db(db_session, uuid4(), 2000.0)

    result = get_all_organization_limits_and_usage_service(db_session, month=12, year=2025)

    assert isinstance(result, list)
    assert any(item.organization_id == ORGANIZATION_ID for item in result)

    delete_organization_limit(db_session, limit_1.id, limit_1.organization_id)
    delete_organization_limit(db_session, limit_2.id, limit_2.organization_id)


def test_upsert_component_version_cost_create(db_session, ensure_component_version):
    """Test creating a new component version cost."""
    component_version_id = ensure_component_version

    result = upsert_component_version_cost_service(
        db_session,
        component_version_id,
        credits_per_call=0.1,
        credits_per={"unit": "second", "value": 0.05},
    )

    assert result.component_version_id == component_version_id
    assert result.credits_per_call == 0.1
    assert result.credits_per == {"unit": "second", "value": 0.05}
    assert result.id is not None

    delete_component_version_cost(db_session, component_version_id)


def test_upsert_component_version_cost_update(db_session, ensure_component_version):
    """Test updating an existing component version cost."""
    component_version_id = ensure_component_version

    create_component_version_cost_in_db(
        db_session,
        component_version_id,
        credits_per_call=0.1,
    )

    result = upsert_component_version_cost_service(
        db_session,
        component_version_id,
        credits_per_call=0.2,
    )

    assert result.component_version_id == component_version_id
    assert result.credits_per_call == 0.2
    assert result.credits_per is None

    delete_component_version_cost(db_session, component_version_id)


def test_upsert_component_version_cost_partial_update(db_session, ensure_component_version):
    """Test partial update of component version cost (only some fields)."""
    component_version_id = ensure_component_version

    create_component_version_cost_in_db(
        db_session,
        component_version_id,
        credits_per_call=0.1,
        credits_per={"unit": "second", "value": 0.05},
    )

    result = upsert_component_version_cost_service(
        db_session,
        component_version_id,
        credits_per_call=0.15,
        credits_per={"unit": "second", "value": 0.05},
    )

    assert result.credits_per_call == 0.15
    assert result.credits_per == {"unit": "second", "value": 0.05}

    delete_component_version_cost(db_session, component_version_id)


def test_delete_component_version_cost_success(db_session, ensure_component_version):
    """Test deleting a component version cost."""
    component_version_id = ensure_component_version

    delete_component_version_cost(db_session, component_version_id)

    create_component_version_cost_in_db(
        db_session,
        component_version_id,
        credits_per_call=0.1,
    )

    delete_component_version_cost_service(db_session, component_version_id)

    cost = (
        db_session.query(db.ComponentCost)
        .filter(db.ComponentCost.component_version_id == component_version_id)
        .first()
    )
    assert cost is None


def test_delete_component_version_cost_not_exists(db_session):
    """Test deleting a component version cost that doesn't exist (should succeed)."""
    component_version_id = uuid4()  # Use a non-existent ID

    delete_component_version_cost_service(db_session, component_version_id)


def test_upsert_component_version_cost_empty_payload(db_session, ensure_component_version):
    """Test upserting with an empty payload (all None values)."""
    component_version_id = ensure_component_version

    result = upsert_component_version_cost_service(
        db_session,
        component_version_id,
        credits_per_call=None,
        credits_per=None,
    )

    assert result.component_version_id == component_version_id
    assert result.credits_per_call is None
    assert result.credits_per is None

    delete_component_version_cost(db_session, component_version_id)


@pytest.mark.asyncio
async def test_llm_credits_count_as_usage_flag(db_session):
    """Test that LLM credits are counted in Usage table only when not using org API key."""
    with get_db_session() as session:
        project_id, graph_runner_id = create_project_and_graph_runner(
            session, project_name_prefix="credits_test", organization_id=ORGANIZATION_ID
        )
        fake_model_name = f"test-model-{uuid4()}"
        fake_model = create_llm_model(session, "Test Model", "Test model", ["completion"], "google", fake_model_name)
        mock_credits_per_input_token = 1000000.0
        mock_credits_per_output_token = 2000000.0
        mock_credits_per_call = 5.0
        create_llm_cost(
            session,
            fake_model.id,
            credits_per_input_token=mock_credits_per_input_token,
            credits_per_output_token=mock_credits_per_output_token,
        )

        ai_agent_version_id = COMPONENT_VERSION_UUIDS["base_ai_agent"]
        upsert_component_version_cost(session, ai_agent_version_id, credits_per_call=mock_credits_per_call)

        start_id = str(uuid4())
        ai_agent_id = str(uuid4())
        edge_id = uuid4()
        graph_payload = GraphUpdateSchema(
            component_instances=[
                ComponentInstanceSchema(
                    id=start_id,
                    component_id=COMPONENT_UUIDS["start"],
                    component_version_id=COMPONENT_VERSION_UUIDS["start_v2"],
                    name="Start",
                    parameters=[
                        PipelineParameterSchema(
                            name="payload_schema",
                            value='{"messages": [{"role": "user", "content": "{{input}}"}]}',
                        )
                    ],
                    is_start_node=True,
                ),
                ComponentInstanceSchema(
                    id=ai_agent_id,
                    component_id=COMPONENT_UUIDS["base_ai_agent"],
                    component_version_id=ai_agent_version_id,
                    name="AI Agent",
                    parameters=[
                        PipelineParameterSchema(name="completion_model", value=f"google:{fake_model_name}"),
                    ],
                    is_start_node=False,
                ),
            ],
            relationships=[],
            edges=[
                EdgeSchema(
                    id=edge_id,
                    origin=UUID(start_id),
                    destination=UUID(ai_agent_id),
                    order=0,
                )
            ],
            port_mappings=[],
        )
        await update_graph_service(session, graph_runner_id, project_id, graph_payload)
        mock_input_tokens = 10
        mock_output_tokens = 20

        mock_response = ("response", mock_input_tokens, mock_output_tokens, mock_input_tokens + mock_output_tokens)

        # Setup trace manager
        trace_manager = TraceManager(project_name="credits-test")
        set_trace_manager(trace_manager)

        # Setup request context (required for credit calculator cache)
        request_ctx = RequestContext(request_id=uuid4())
        set_request_context(request_ctx)

        # Case 1: No org secret (DraftNRun API key)
        setup_tracing_context(session, project_id)
        with patch(
            "engine.llm_services.providers.google_provider.GoogleProvider.complete", new_callable=AsyncMock
        ) as mock_complete:
            mock_complete.return_value = mock_response
            result = await run_env_agent(
                session,
                project_id,
                db.EnvType.DRAFT,
                {"messages": [{"role": "user", "content": "test"}]},
                db.CallType.SANDBOX,
            )
            assert result.error is None
        trace_manager.force_flush()

        # Credit calculator divides by 1_000_000 (credits_per_token is per million tokens)
        mock_credits_input_token = mock_credits_per_input_token * mock_input_tokens / 1_000_000
        mock_credits_output_token = mock_credits_per_output_token * mock_output_tokens / 1_000_000

        # Case 1: Query most recent LLM span (with model_id) and component span (with component_instance_id)
        llm_span_usage_case1 = session.execute(
            select(SpanUsage)
            .join(Span, SpanUsage.span_id == Span.span_id)
            .where(Span.model_id == fake_model.id, Span.project_id == str(project_id))
            .order_by(Span.start_time.desc())
            .limit(1)
        ).scalar_one_or_none()
        assert llm_span_usage_case1 is not None, "Case 1: LLM span usage should exist"
        assert llm_span_usage_case1.credits_input_token == mock_credits_input_token
        assert llm_span_usage_case1.credits_output_token == mock_credits_output_token
        assert llm_span_usage_case1.credits_per_call is None, "Case 1: LLM span should not have component credits"

        component_span_usage_case1 = session.execute(
            select(SpanUsage)
            .join(Span, SpanUsage.span_id == Span.span_id)
            .where(Span.component_instance_id == UUID(ai_agent_id), Span.project_id == str(project_id))
            .order_by(Span.start_time.desc())
            .limit(1)
        ).scalar_one_or_none()
        assert component_span_usage_case1 is not None, "Case 1: Component span usage should exist"
        assert component_span_usage_case1.credits_per_call == mock_credits_per_call
        assert component_span_usage_case1.credits_input_token is None, (
            "Case 1: Component span should not have LLM token credits"
        )
        assert component_span_usage_case1.credits_output_token is None, (
            "Case 1: Component span should not have LLM token credits"
        )

        now = datetime.now()
        usage = session.execute(
            select(Usage).where(Usage.project_id == project_id, Usage.year == now.year, Usage.month == now.month)
        ).scalar_one_or_none()
        assert usage is not None
        case1_credits = usage.credits_used
        assert case1_credits == mock_credits_input_token + mock_credits_output_token + mock_credits_per_call

        # Case 2: Create org secret (org API key)
        upsert_organization_secret(session, ORGANIZATION_ID, "google_api_key", "org-key", db.OrgSecretType.LLM_API_KEY)
        setup_tracing_context(session, project_id)

        with patch(
            "engine.llm_services.providers.google_provider.GoogleProvider.complete", new_callable=AsyncMock
        ) as mock_complete:
            mock_complete.return_value = mock_response
            result = await run_env_agent(
                session,
                project_id,
                db.EnvType.DRAFT,
                {"messages": [{"role": "user", "content": "test"}]},
                db.CallType.SANDBOX,
            )
            assert result.error is None
        trace_manager.force_flush()

        # Case 2: Query most recent LLM span (with model_id) and component span (with component_instance_id)
        # These will be from Case 2 since they're ordered by start_time desc
        llm_span_usage_case2 = session.execute(
            select(SpanUsage)
            .join(Span, SpanUsage.span_id == Span.span_id)
            .where(Span.model_id == fake_model.id, Span.project_id == str(project_id))
            .order_by(Span.start_time.desc())
            .limit(1)
        ).scalar_one_or_none()
        assert llm_span_usage_case2 is not None, "Case 2: LLM span usage should exist"
        assert llm_span_usage_case2.credits_input_token == mock_credits_input_token
        assert llm_span_usage_case2.credits_output_token == mock_credits_output_token
        # In Case 2, LLM credits should NOT count towards Usage (count_as_usage=False)
        # But they should still be stored in SpanUsage for tracking

        component_span_usage_case2 = session.execute(
            select(SpanUsage)
            .join(Span, SpanUsage.span_id == Span.span_id)
            .where(Span.component_instance_id == UUID(ai_agent_id), Span.project_id == str(project_id))
            .order_by(Span.start_time.desc())
            .limit(1)
        ).scalar_one_or_none()
        assert component_span_usage_case2 is not None, "Case 2: Component span usage should exist"
        assert component_span_usage_case2.credits_per_call == mock_credits_per_call, (
            "Case 2: Component span should have credit per call"
        )
        # Component credits should always count (count_as_usage=True)

        usage = session.execute(
            select(Usage).where(Usage.project_id == project_id, Usage.year == now.year, Usage.month == now.month)
        ).scalar_one_or_none()
        assert usage is not None
        case2_credits = usage.credits_used
        # Case 2: Only component cost should be added (LLM credits don't count due to org API key)
        assert case2_credits == case1_credits + mock_credits_per_call

        limits_usage = get_all_organization_limits_and_usage_service(session, now.month, now.year)
        org_usage = next((item for item in limits_usage if item.organization_id == ORGANIZATION_ID), None)
        assert org_usage is not None
        assert org_usage.total_credits_used == case2_credits

        session.query(Span).filter(Span.project_id == str(project_id)).delete()
        session.commit()

        delete_llm_model_service(session, fake_model.id)

        delete_project_service(session, project_id)

        try:
            delete_organization_secret(session, ORGANIZATION_ID, "google_api_key")
        except Exception:
            pass
