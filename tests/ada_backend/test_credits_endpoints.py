from uuid import UUID, uuid4
import pytest
from unittest.mock import patch

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


def create_component_version_cost_in_db(session, component_version_id: UUID, **kwargs):
    """Helper to create a component version cost in the database using repository function."""
    return create_component_version_cost(
        session,
        component_version_id,
        credits_per_call=kwargs.get("credits_per_call"),
        credits_per_unit=kwargs.get("credits_per_unit"),
    )


def create_organization_limit_in_db(session, organization_id: UUID, limit: float):
    """Helper to create an organization limit in the database using repository function."""
    return create_organization_limit(session, organization_id, limit)


def test_get_all_organization_limits(db_session):
    """Test getting all organization limits."""
    org_id_1 = UUID(ORGANIZATION_ID)
    org_id_2 = uuid4()

    # Clean up existing limits using repository function
    existing_limits = get_all_organization_limits(db_session)
    for limit in existing_limits:
        if limit.organization_id in [org_id_1, org_id_2]:
            delete_organization_limit(db_session, limit.id, limit.organization_id)

    limit_1 = create_organization_limit_in_db(db_session, org_id_1, 1000.0)
    limit_2 = create_organization_limit_in_db(db_session, org_id_2, 2000.0)

    response = client.get(
        "/organizations-limits",
        headers=HEADERS_JWT,
    )

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 2

    for limit in data:
        assert "id" in limit
        assert "organization_id" in limit
        assert "limit" in limit
        assert "created_at" in limit
        assert "updated_at" in limit

    delete_organization_limit(db_session, limit_1.id, limit_1.organization_id)
    delete_organization_limit(db_session, limit_2.id, limit_2.organization_id)


@patch("ada_backend.services.user_roles_service.is_user_super_admin")
def test_create_organization_limit_success(mock_is_super_admin, db_session):
    """Test creating an organization limit as super admin."""
    mock_is_super_admin.return_value = True
    org_id = UUID(ORGANIZATION_ID)

    # Clean up existing limit if it exists
    existing_limits = get_all_organization_limits(db_session)
    for limit in existing_limits:
        if limit.organization_id == org_id:
            delete_organization_limit(db_session, limit.id, limit.organization_id)

    payload = {
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
    assert data["limit"] == 5000.0
    assert "id" in data
    assert "created_at" in data
    assert "updated_at" in data

    limit_id = UUID(data["id"])
    delete_organization_limit(db_session, limit_id, org_id)


@patch("ada_backend.services.user_roles_service.is_user_super_admin")
def test_update_organization_limit_success(mock_is_super_admin, db_session):
    """Test updating an organization limit as super admin."""
    mock_is_super_admin.return_value = True
    org_id = UUID(ORGANIZATION_ID)

    # Clean up existing limit if it exists
    existing_limits = get_all_organization_limits(db_session)
    for limit in existing_limits:
        if limit.organization_id == org_id:
            delete_organization_limit(db_session, limit.id, limit.organization_id)

    org_limit = create_organization_limit_in_db(db_session, org_id, 3000.0)
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

    delete_organization_limit(db_session, limit_id, org_id)


@patch("ada_backend.services.user_roles_service.is_user_super_admin")
def test_update_organization_limit_not_found(mock_is_super_admin):
    """Test updating a non-existent organization limit."""
    mock_is_super_admin.return_value = True
    org_id = UUID(ORGANIZATION_ID)
    fake_limit_id = uuid4()
    new_limit = 6000.0

    response = client.patch(
        f"/organizations/{org_id}/organization-limits?id={fake_limit_id}&organization_limit={new_limit}",
        headers=HEADERS_JWT,
    )

    assert response.status_code == 404


@patch("ada_backend.services.user_roles_service.is_user_super_admin")
def test_delete_organization_limit_success(mock_is_super_admin, db_session):
    """Test deleting an organization limit as super admin."""
    mock_is_super_admin.return_value = True
    org_id = UUID(ORGANIZATION_ID)

    existing_limits = get_all_organization_limits(db_session)
    for limit in existing_limits:
        if limit.organization_id == org_id:
            delete_organization_limit(db_session, limit.id, limit.organization_id)

    org_limit = create_organization_limit_in_db(db_session, org_id, 4000.0)
    limit_id = org_limit.id

    response = client.delete(
        f"/organizations/{org_id}/organization-limits?id={limit_id}",
        headers=HEADERS_JWT,
    )

    assert response.status_code == 204

    # Verify deletion - query should return empty list or not contain this limit
    all_limits = get_all_organization_limits(db_session)
    limit_ids = [limit.id for limit in all_limits]
    assert limit_id not in limit_ids


@patch("ada_backend.services.user_roles_service.is_user_super_admin")
def test_create_organization_limit_duplicate(mock_is_super_admin, db_session):
    """Test creating a duplicate organization limit (same org) should fail."""
    mock_is_super_admin.return_value = True
    org_id = UUID(ORGANIZATION_ID)

    # Clean up any existing limit first
    existing_limits = get_all_organization_limits(db_session)
    for limit in existing_limits:
        if limit.organization_id == org_id:
            delete_organization_limit(db_session, limit.id, limit.organization_id)

    org_limit = create_organization_limit_in_db(db_session, org_id, 5000.0)

    payload = {
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


@patch("ada_backend.services.user_roles_service.is_user_super_admin")
def test_create_organization_limit_missing_fields(mock_is_super_admin, db_session):
    """Test creating an organization limit with missing required fields."""
    mock_is_super_admin.return_value = True
    org_id = UUID(ORGANIZATION_ID)

    # Clean up existing limit if it exists
    existing_limits = get_all_organization_limits(db_session)
    for limit in existing_limits:
        if limit.organization_id == org_id:
            delete_organization_limit(db_session, limit.id, limit.organization_id)

    payload = {}

    response = client.post(
        f"/organizations/{org_id}/organization-limits",
        headers=HEADERS_JWT,
        json=payload,
    )

    # Should still succeed with default limit of 0.0
    assert response.status_code == 200
    data = response.json()
    assert data["limit"] == 0.0

    # Clean up
    limit_id = UUID(data["id"])
    delete_organization_limit(db_session, limit_id, org_id)


@patch("ada_backend.services.user_roles_service.is_user_super_admin")
def test_update_organization_limit_same_value(mock_is_super_admin, db_session):
    """Test updating an organization limit with the same value."""
    mock_is_super_admin.return_value = True
    org_id = UUID(ORGANIZATION_ID)

    # Clean up existing limit if it exists
    existing_limits = get_all_organization_limits(db_session)
    for limit in existing_limits:
        if limit.organization_id == org_id:
            delete_organization_limit(db_session, limit.id, limit.organization_id)

    org_limit = create_organization_limit_in_db(db_session, org_id, 5000.0)
    limit_id = org_limit.id

    response = client.patch(
        f"/organizations/{org_id}/organization-limits?id={limit_id}&organization_limit=5000.0",
        headers=HEADERS_JWT,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["limit"] == 5000.0

    delete_organization_limit(db_session, limit_id, org_id)


@patch("ada_backend.services.user_roles_service.is_user_super_admin")
def test_update_organization_limit_zero_limit(mock_is_super_admin, db_session):
    """Test updating an organization limit with zero limit."""
    mock_is_super_admin.return_value = True
    org_id = UUID(ORGANIZATION_ID)

    # Clean up existing limit if it exists
    existing_limits = get_all_organization_limits(db_session)
    for limit in existing_limits:
        if limit.organization_id == org_id:
            delete_organization_limit(db_session, limit.id, limit.organization_id)

    org_limit = create_organization_limit_in_db(db_session, org_id, 1000.0)
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
    """Test getting all organization limits."""
    org_id = UUID(ORGANIZATION_ID)

    # Clean up existing limits
    existing_limits = get_all_organization_limits(db_session)
    for limit in existing_limits:
        if limit.organization_id == org_id:
            delete_organization_limit(db_session, limit.id, limit.organization_id)

    limit_1 = create_organization_limit_in_db(db_session, org_id, 1000.0)
    limit_2 = create_organization_limit_in_db(db_session, uuid4(), 2000.0)

    response = client.get(
        "/organizations-limits",
        headers=HEADERS_JWT,
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert any(limit["id"] == str(limit_1.id) for limit in data)
    assert any(limit["id"] == str(limit_2.id) for limit in data)

    delete_organization_limit(db_session, limit_1.id, limit_1.organization_id)
    delete_organization_limit(db_session, limit_2.id, limit_2.organization_id)


@patch("ada_backend.services.user_roles_service.is_user_super_admin")
def test_upsert_component_version_cost_create(mock_is_super_admin, db_session, ensure_component_version):
    """Test creating a new component version cost."""
    mock_is_super_admin.return_value = True
    component_version_id = ensure_component_version

    payload = {
        "credits_per_call": 0.1,
        "credits_per_unit": {"unit": "second", "value": 0.05},
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
    assert data["credits_per_unit"] == {"unit": "second", "value": 0.05}
    assert "id" in data

    delete_component_version_cost(db_session, component_version_id)


@patch("ada_backend.services.user_roles_service.is_user_super_admin")
def test_upsert_component_version_cost_update(mock_is_super_admin, db_session, ensure_component_version):
    """Test updating an existing component version cost."""
    mock_is_super_admin.return_value = True
    component_version_id = ensure_component_version

    create_component_version_cost_in_db(
        db_session,
        component_version_id,
        credits_per_call=0.1,
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


@patch("ada_backend.services.user_roles_service.is_user_super_admin")
def test_upsert_component_version_cost_partial_update(mock_is_super_admin, db_session, ensure_component_version):
    """Test partial update of component version cost (only some fields)."""
    mock_is_super_admin.return_value = True
    component_version_id = ensure_component_version

    create_component_version_cost_in_db(
        db_session,
        component_version_id,
        credits_per_call=0.1,
        credits_per_unit={"unit": "second", "value": 0.05},
    )

    payload = {
        "credits_per_call": 0.15,
        "credits_per_unit": {"unit": "second", "value": 0.05},
    }

    response = client.patch(
        f"/organizations/{ORGANIZATION_ID}/component-version-costs/{component_version_id}",
        headers=HEADERS_JWT,
        json=payload,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["credits_per_call"] == 0.15
    assert data["credits_per_unit"] == {"unit": "second", "value": 0.05}

    delete_component_version_cost(db_session, component_version_id)


@patch("ada_backend.services.user_roles_service.is_user_super_admin")
def test_delete_component_version_cost_success(mock_is_super_admin, db_session, ensure_component_version):
    """Test deleting a component version cost."""
    mock_is_super_admin.return_value = True
    component_version_id = ensure_component_version

    # Clean up any existing cost first
    delete_component_version_cost(db_session, component_version_id)

    create_component_version_cost_in_db(
        db_session,
        component_version_id,
        credits_per_call=0.1,
    )

    response = client.delete(
        f"/organizations/{ORGANIZATION_ID}/component-version-costs/{component_version_id}",
        headers=HEADERS_JWT,
    )

    assert response.status_code == 204


@patch("ada_backend.services.user_roles_service.is_user_super_admin")
def test_delete_component_version_cost_not_exists(mock_is_super_admin):
    """Test deleting a component version cost that doesn't exist (should succeed)."""
    mock_is_super_admin.return_value = True
    component_version_id = uuid4()  # Use a non-existent ID

    response = client.delete(
        f"/organizations/{ORGANIZATION_ID}/component-version-costs/{component_version_id}",
        headers=HEADERS_JWT,
    )
    assert response.status_code == 204


@patch("ada_backend.services.user_roles_service.is_user_super_admin")
def test_upsert_component_version_cost_empty_payload(mock_is_super_admin, db_session, ensure_component_version):
    """Test upserting with an empty payload (all None values)."""
    mock_is_super_admin.return_value = True
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
