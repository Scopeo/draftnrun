"""Tests for field_expression_repository functions."""

from ada_backend.database.setup_db import get_db_session
from ada_backend.repositories import field_expression_repository


def test_create_field_expression():
    """Test creating a field expression."""
    with get_db_session() as session:
        expr = field_expression_repository.create_field_expression(
            session=session,
            expression_json={"type": "literal", "value": "test"},
        )

        assert expr.id is not None
        assert expr.expression_json == {"type": "literal", "value": "test"}


def test_get_field_expression():
    """Test retrieving a field expression by ID."""
    with get_db_session() as session:
        created_expr = field_expression_repository.create_field_expression(
            session=session,
            expression_json={"type": "literal", "value": "test"},
        )

        retrieved_expr = field_expression_repository.get_field_expression(
            session=session,
            field_expression_id=created_expr.id,
        )

        assert retrieved_expr is not None
        assert retrieved_expr.id == created_expr.id
        assert retrieved_expr.expression_json == {"type": "literal", "value": "test"}


def test_update_field_expression():
    """Test updating a field expression."""
    with get_db_session() as session:
        expr = field_expression_repository.create_field_expression(
            session=session,
            expression_json={"type": "literal", "value": "original"},
        )

        updated_expr = field_expression_repository.update_field_expression(
            session=session,
            field_expression_id=expr.id,
            expression_json={"type": "literal", "value": "updated"},
        )

        assert updated_expr is not None
        assert updated_expr.id == expr.id
        assert updated_expr.expression_json == {"type": "literal", "value": "updated"}


def test_delete_field_expression():
    """Test deleting a field expression."""
    with get_db_session() as session:
        expr = field_expression_repository.create_field_expression(
            session=session,
            expression_json={"type": "literal", "value": "test"},
        )

        result = field_expression_repository.delete_field_expression_by_id(
            session=session,
            field_expression_id=expr.id,
        )

        assert result is True

        # Verify it's deleted
        retrieved = field_expression_repository.get_field_expression(
            session=session,
            field_expression_id=expr.id,
        )
        assert retrieved is None
