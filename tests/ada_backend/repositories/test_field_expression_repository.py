"""Tests for field_expression_repository functions."""

import uuid

import pytest
from sqlalchemy.orm import Session

from ada_backend.database import models as db
from ada_backend.repositories import field_expression_repository


@pytest.fixture
def test_component_instance(ada_backend_mock_session: Session):
    """Create a test component instance."""
    component = db.Component(
        id=uuid.uuid4(),
        name="Test Component",
        description="Test component for field expressions",
    )
    ada_backend_mock_session.add(component)
    ada_backend_mock_session.flush()

    component_version = db.ComponentVersion(
        id=uuid.uuid4(),
        component_id=component.id,
        version="1.0.0",
    )
    ada_backend_mock_session.add(component_version)
    ada_backend_mock_session.flush()

    component_instance = db.ComponentInstance(
        id=uuid.uuid4(),
        component_version_id=component_version.id,
        name="Test Instance",
    )
    ada_backend_mock_session.add(component_instance)
    ada_backend_mock_session.commit()

    return component_instance


def test_create_field_expression(ada_backend_mock_session: Session):
    """Test creating a field expression."""
    expr = field_expression_repository.create_field_expression(
        session=ada_backend_mock_session,
        expression_json={"type": "literal", "value": "test"},
    )

    assert expr.id is not None
    assert expr.expression_json == {"type": "literal", "value": "test"}


def test_get_field_expression(ada_backend_mock_session: Session):
    """Test retrieving a field expression by ID."""
    created_expr = field_expression_repository.create_field_expression(
        session=ada_backend_mock_session,
        expression_json={"type": "literal", "value": "test"},
    )

    retrieved_expr = field_expression_repository.get_field_expression(
        session=ada_backend_mock_session,
        field_expression_id=created_expr.id,
    )

    assert retrieved_expr is not None
    assert retrieved_expr.id == created_expr.id
    assert retrieved_expr.expression_json == {"type": "literal", "value": "test"}


def test_update_field_expression(ada_backend_mock_session: Session):
    """Test updating a field expression."""
    expr = field_expression_repository.create_field_expression(
        session=ada_backend_mock_session,
        expression_json={"type": "literal", "value": "original"},
    )

    updated_expr = field_expression_repository.update_field_expression(
        session=ada_backend_mock_session,
        field_expression_id=expr.id,
        expression_json={"type": "literal", "value": "updated"},
    )

    assert updated_expr is not None
    assert updated_expr.id == expr.id
    assert updated_expr.expression_json == {"type": "literal", "value": "updated"}


def test_delete_field_expression(ada_backend_mock_session: Session):
    """Test deleting a field expression."""
    expr = field_expression_repository.create_field_expression(
        session=ada_backend_mock_session,
        expression_json={"type": "literal", "value": "test"},
    )

    result = field_expression_repository.delete_field_expression_by_id(
        session=ada_backend_mock_session,
        field_expression_id=expr.id,
    )

    assert result is True

    # Verify it's deleted
    retrieved = field_expression_repository.get_field_expression(
        session=ada_backend_mock_session,
        field_expression_id=expr.id,
    )
    assert retrieved is None
