from uuid import UUID, uuid4
import pytest

from fastapi.testclient import TestClient

from ada_backend.main import app
from ada_backend.scripts.get_supabase_token import get_user_jwt
from ada_backend.database.seed.utils import COMPONENT_VERSION_UUIDS
from ada_backend.database.setup_db import SessionLocal
from ada_backend.database import models as db
from ada_backend.repositories.credits_repository import (
    create_organization_limit,
    create_component_version_cost,
    delete_organization_limit,
    delete_component_version_cost,
    get_all_organization_limits,
)
from settings import settings

client = TestClient(app)
ORGANIZATION_ID = "37b7d67f-8f29-4fce-8085-19dea582f605"  # umbrella organization
JWT_TOKEN = get_user_jwt(settings.TEST_USER_EMAIL, settings.TEST_USER_PASSWORD)
HEADERS_JWT = {
    "accept": "application/json",
    "Authorization": f"Bearer {JWT_TOKEN}",
}
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


@pytest.fixture
def unique_year_month():
    """Generate unique year/month combination to avoid constraint violations in parallel tests."""
    unique_year = 2099
    unique_month = (uuid4().int % 12) + 1  # 1-12, more unique for parallel runs
    return unique_year, unique_month


def create_component_version_cost_in_db(session, component_version_id: UUID, **kwargs):
    """Helper to create a component version cost in the database using repository function."""
    return create_component_version_cost(
        session,
        component_version_id,
        credits_per_call=kwargs.get("credits_per_call"),
        credits_per_unit=kwargs.get("credits_per_unit"),
    )


def create_organization_limit_in_db(session, organization_id: UUID, year: int, month: int, limit: float):
    """Helper to create an organization limit in the database using repository function."""
    return create_organization_limit(session, organization_id, year, month, limit)


def test_get_all_organization_limits(db_session):
    """Test getting all organization limits for a specific year and month."""
    test_year = 2098
    test_month = (uuid4().int % 12) + 1

    org_id_1 = UUID(ORGANIZATION_ID)
    org_id_2 = uuid4()

    # Clean up existing limits using repository function
    existing_limits = get_all_organization_limits(db_session, test_year, test_month)
    for limit in existing_limits:
        if limit.organization_id in [org_id_1, org_id_2]:
            delete_organization_limit(db_session, limit.id, limit.organization_id)

    other_month = test_month + 1 if test_month < 12 else 1
    existing_limits_other = get_all_organization_limits(db_session, test_year, other_month)
    for limit in existing_limits_other:
        if limit.organization_id == org_id_1:
            delete_organization_limit(db_session, limit.id, limit.organization_id)

    limit_1 = create_organization_limit_in_db(db_session, org_id_1, test_year, test_month, 1000.0)
    limit_2 = create_organization_limit_in_db(db_session, org_id_2, test_year, test_month, 2000.0)

    other_month = test_month + 1 if test_month < 12 else 1
    limit_3 = create_organization_limit_in_db(db_session, org_id_1, test_year, other_month, 1500.0)

    response = client.get(f"/organizations-limits?year={test_year}&month={test_month}")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 2

    for limit in data:
        assert "id" in limit
        assert "organization_id" in limit
        assert "year" in limit
        assert "month" in limit
        assert "limit" in limit
        assert "created_at" in limit
        assert "updated_at" in limit
        assert limit["year"] == test_year
        assert limit["month"] == test_month

    delete_organization_limit(db_session, limit_1.id, limit_1.organization_id)
    delete_organization_limit(db_session, limit_2.id, limit_2.organization_id)
    delete_organization_limit(db_session, limit_3.id, limit_3.organization_id)


def test_create_organization_limit_success(db_session, unique_year_month):
    """Test creating an organization limit as super admin."""
    org_id = UUID(ORGANIZATION_ID)
    unique_year, unique_month = unique_year_month

    # Clean up existing limit if it exists
    existing_limits = get_all_organization_limits(db_session, unique_year, unique_month)
    for limit in existing_limits:
        if limit.organization_id == org_id:
            delete_organization_limit(db_session, limit.id, limit.organization_id)

    payload = {
        "year": unique_year,
        "month": unique_month,
        "limit": 5000.0,
    }

    response = client.post(
        f"/organizations/{org_id}/organization-limits",
        headers=HEADERS_JWT,
        json=payload,
    )

    if response.status_code != 200:
        print(f"Unexpected status code: {response.status_code}")
        print(f"Response: {response.json()}")

    assert response.status_code == 200, f"Expected 200 but got {response.status_code}: {response.json()}"
    data = response.json()
    assert data["organization_id"] == str(org_id)
    assert data["year"] == unique_year
    assert data["month"] == unique_month
    assert data["limit"] == 5000.0
    assert "id" in data
    assert "created_at" in data
    assert "updated_at" in data

    limit_id = UUID(data["id"])
    delete_organization_limit(db_session, limit_id, org_id)


def test_update_organization_limit_success(db_session):
    """Test updating an organization limit as super admin."""
    org_id = UUID(ORGANIZATION_ID)
    org_limit = create_organization_limit_in_db(db_session, org_id, 2025, 2, 3000.0)
    limit_id = org_limit.id

    new_limit = 6000.0
    response = client.patch(
        f"/organizations/{org_id}/organization-limits?id={limit_id}&organization_limit={new_limit}",
        headers=HEADERS_JWT,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(limit_id)
    assert data["organization_id"] == str(org_id)
    assert data["limit"] == new_limit
    assert data["year"] == 2025
    assert data["month"] == 2

    delete_organization_limit(db_session, limit_id, org_id)


def test_update_organization_limit_not_found():
    """Test updating a non-existent organization limit."""
    org_id = UUID(ORGANIZATION_ID)
    fake_limit_id = uuid4()
    new_limit = 6000.0

    response = client.patch(
        f"/organizations/{org_id}/organization-limits?id={fake_limit_id}&organization_limit={new_limit}",
        headers=HEADERS_JWT,
    )

    assert response.status_code == 404


def test_delete_organization_limit_success(db_session):
    """Test deleting an organization limit as super admin."""
    org_id = UUID(ORGANIZATION_ID)
    org_limit = create_organization_limit_in_db(db_session, org_id, 2025, 3, 4000.0)
    limit_id = org_limit.id

    response = client.delete(
        f"/organizations/{org_id}/organization-limits?id={limit_id}",
        headers=HEADERS_JWT,
    )

    assert response.status_code == 204

    # Verify deletion - query should return empty list or not contain this limit
    all_limits = get_all_organization_limits(db_session, 2025, 3)
    limit_ids = [limit.id for limit in all_limits]
    assert limit_id not in limit_ids


def test_create_organization_limit_duplicate(db_session, unique_year_month):
    """Test creating a duplicate organization limit (same org, year, month) should fail."""
    org_id = UUID(ORGANIZATION_ID)
    unique_year, unique_month = unique_year_month

    org_limit = create_organization_limit_in_db(db_session, org_id, unique_year, unique_month, 5000.0)

    payload = {
        "year": unique_year,
        "month": unique_month,
        "limit": 6000.0,
    }

    response = client.post(
        f"/organizations/{org_id}/organization-limits",
        headers=HEADERS_JWT,
        json=payload,
    )

    assert response.status_code == 500
    assert "Internal server error" in response.json()["detail"]

    delete_organization_limit(db_session, org_limit.id, org_id)


def test_create_organization_limit_missing_fields():
    """Test creating an organization limit with missing required fields."""
    org_id = UUID(ORGANIZATION_ID)
    payload = {
        "year": 2025,
    }

    response = client.post(
        f"/organizations/{org_id}/organization-limits",
        headers=HEADERS_JWT,
        json=payload,
    )

    assert response.status_code in [400, 422]


def test_update_organization_limit_same_value(db_session):
    """Test updating an organization limit with the same value."""
    org_id = UUID(ORGANIZATION_ID)
    org_limit = create_organization_limit_in_db(db_session, org_id, 2025, 4, 5000.0)
    limit_id = org_limit.id

    response = client.patch(
        f"/organizations/{org_id}/organization-limits?id={limit_id}&organization_limit=5000.0",
        headers=HEADERS_JWT,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["limit"] == 5000.0

    delete_organization_limit(db_session, limit_id, org_id)


def test_update_organization_limit_zero_limit(db_session):
    """Test updating an organization limit with zero limit."""
    org_id = UUID(ORGANIZATION_ID)
    org_limit = create_organization_limit_in_db(db_session, org_id, 2025, 5, 1000.0)
    limit_id = org_limit.id

    response = client.patch(
        f"/organizations/{org_id}/organization-limits?id={limit_id}&organization_limit=0.0",
        headers=HEADERS_JWT,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["limit"] == 0.0

    delete_organization_limit(db_session, limit_id, org_id)


def test_get_all_organization_limits_with_filters(db_session):
    """Test getting organization limits with different year/month filters."""
    org_id = UUID(ORGANIZATION_ID)

    test_year = 2097
    month_1 = (uuid4().int % 12) + 1
    month_2 = ((uuid4().int % 11) + 1) if month_1 == 12 else (month_1 + 1 if month_1 < 12 else 1)
    month_3 = ((uuid4().int % 10) + 1) if month_2 == 12 else (month_2 + 1 if month_2 < 12 else 1)

    # Clean up existing limits
    for month in [month_1, month_2, month_3]:
        existing_limits = get_all_organization_limits(db_session, test_year, month)
        for limit in existing_limits:
            if limit.organization_id == org_id:
                delete_organization_limit(db_session, limit.id, limit.organization_id)

    limit_1 = create_organization_limit_in_db(db_session, org_id, test_year, month_1, 1000.0)
    limit_2 = create_organization_limit_in_db(db_session, org_id, test_year, month_2, 2000.0)
    limit_3 = create_organization_limit_in_db(db_session, org_id, test_year, month_3, 3000.0)

    response = client.get(f"/organizations-limits?year={test_year}&month={month_1}")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert any(limit["id"] == str(limit_1.id) for limit in data)

    response = client.get(f"/organizations-limits?year={test_year}&month={month_2}")
    assert response.status_code == 200
    data = response.json()
    assert any(limit["id"] == str(limit_2.id) for limit in data)

    delete_organization_limit(db_session, limit_1.id, limit_1.organization_id)
    delete_organization_limit(db_session, limit_2.id, limit_2.organization_id)
    delete_organization_limit(db_session, limit_3.id, limit_3.organization_id)


def test_upsert_component_version_cost_create(db_session, ensure_component_version):
    """Test creating a new component version cost."""
    component_version_id = ensure_component_version

    payload = {
        "credits_per_call": 0.1,
        "credits_per_unit": 0.05,
    }

    response = client.patch(
        f"/organizations/{ORGANIZATION_ID}/component-version-costs/{component_version_id}",
        headers=HEADERS_JWT,
        json=payload,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["component_version_id"] == str(component_version_id)
    assert data["credits_per_call"] == 0.1
    assert data["credits_per_unit"] == 0.05
    assert "id" in data

    delete_component_version_cost(db_session, component_version_id)


def test_upsert_component_version_cost_update(db_session, ensure_component_version):
    """Test updating an existing component version cost."""
    component_version_id = ensure_component_version

    create_component_version_cost_in_db(
        db_session,
        component_version_id,
    )

    payload = {
        "credits_per_call": 0.2,
    }

    response = client.patch(
        f"/organizations/{ORGANIZATION_ID}/component-version-costs/{component_version_id}",
        headers=HEADERS_JWT,
        json=payload,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["component_version_id"] == str(component_version_id)
    assert data["credits_per_call"] == 0.2
    assert data["credits_per_unit"] is None

    delete_component_version_cost(db_session, component_version_id)


def test_upsert_component_version_cost_partial_update(db_session, ensure_component_version):
    """Test partial update of component version cost (only some fields)."""
    component_version_id = ensure_component_version

    create_component_version_cost_in_db(
        db_session,
        component_version_id,
        credits_per_call=0.1,
        credits_per_unit=0.05,
    )

    payload = {
        "credits_per_call": 0.1,
        "credits_per_unit": 0.05,
    }

    response = client.patch(
        f"/organizations/{ORGANIZATION_ID}/component-version-costs/{component_version_id}",
        headers=HEADERS_JWT,
        json=payload,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["credits_per_call"] == 0.1
    assert data["credits_per_unit"] == 0.05

    delete_component_version_cost(db_session, component_version_id)


def test_delete_component_version_cost_success(db_session, ensure_component_version):
    """Test deleting a component version cost."""
    component_version_id = ensure_component_version

    # Clean up any existing cost first
    delete_component_version_cost(db_session, component_version_id)

    create_component_version_cost_in_db(
        db_session,
        component_version_id,
    )

    response = client.delete(
        f"/organizations/{ORGANIZATION_ID}/component-version-costs/{component_version_id}",
        headers=HEADERS_JWT,
    )

    assert response.status_code == 204


def test_delete_component_version_cost_not_exists():
    """Test deleting a component version cost that doesn't exist (should succeed)."""
    component_version_id = uuid4()  # Use a non-existent ID

    response = client.delete(
        f"/organizations/{ORGANIZATION_ID}/component-version-costs/{component_version_id}",
        headers=HEADERS_JWT,
    )
    assert response.status_code == 204


def test_upsert_component_version_cost_empty_payload(db_session, ensure_component_version):
    """Test upserting with an empty payload (all None values)."""
    component_version_id = ensure_component_version

    payload = {}

    response = client.patch(
        f"/organizations/{ORGANIZATION_ID}/component-version-costs/{component_version_id}",
        headers=HEADERS_JWT,
        json=payload,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["component_version_id"] == str(component_version_id)
    assert data["credits_per_call"] is None
    assert data["credits_per_unit"] is None

    delete_component_version_cost(db_session, component_version_id)
