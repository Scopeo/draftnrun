from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from ada_backend.database import models as db
from ada_backend.database.seed.utils import COMPONENT_VERSION_UUIDS
from ada_backend.database.setup_db import SessionLocal
from ada_backend.repositories.credits_repository import (
    create_component_version_cost,
    create_organization_limit,
    delete_component_version_cost,
    delete_organization_limit,
)
from ada_backend.services.credits_service import (
    create_organization_limit_service,
    delete_component_version_cost_service,
    delete_organization_limit_service,
    get_all_organization_limits_and_usage_service,
    update_organization_limit_service,
    upsert_component_version_cost_service,
)
from ada_backend.services.errors import OrganizationLimitNotFound

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
