"""Tests for input_port_instance_repository functions."""

import uuid

import pytest
from sqlalchemy.orm import Session

from ada_backend.database import models as db
from ada_backend.repositories import input_port_instance_repository


@pytest.fixture
def test_component_instance(ada_backend_mock_session: Session):
    """Create a test component instance."""
    component = db.Component(
        id=uuid.uuid4(),
        name="Test Component",
        description="Test component for port instances",
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


@pytest.fixture
def test_port_definition(ada_backend_mock_session: Session, test_component_instance):
    """Create a test port definition."""
    port_def = db.PortDefinition(
        id=uuid.uuid4(),
        component_version_id=test_component_instance.component_version_id,
        name="test_port",
        port_type=db.PortType.INPUT,
        is_canonical=False,
    )
    ada_backend_mock_session.add(port_def)
    ada_backend_mock_session.commit()
    return port_def


@pytest.fixture
def test_field_expression(ada_backend_mock_session: Session):
    """Create a test field expression."""
    field_expr = db.FieldExpression(
        id=uuid.uuid4(),
        expression_json={"type": "literal", "value": "test"},
    )
    ada_backend_mock_session.add(field_expr)
    ada_backend_mock_session.commit()
    return field_expr


def test_create_input_port_instance(ada_backend_mock_session: Session, test_component_instance):
    """Test creating an input port instance."""
    port = input_port_instance_repository.create_input_port_instance(
        session=ada_backend_mock_session,
        component_instance_id=test_component_instance.id,
        name="test_input_port",
        description="A test input port",
    )

    assert port.id is not None
    assert port.component_instance_id == test_component_instance.id
    assert port.name == "test_input_port"
    assert port.description == "A test input port"
    assert port.port_definition_id is None
    assert port.field_expression_id is None


def test_create_input_port_instance_with_references(
    ada_backend_mock_session: Session,
    test_component_instance,
    test_port_definition,
    test_field_expression,
):
    """Test creating an input port instance with port definition and field expression."""
    port = input_port_instance_repository.create_input_port_instance(
        session=ada_backend_mock_session,
        component_instance_id=test_component_instance.id,
        name="test_input_port",
        port_definition_id=test_port_definition.id,
        field_expression_id=test_field_expression.id,
        description="Port with references",
    )

    assert port.id is not None
    assert port.port_definition_id == test_port_definition.id
    assert port.field_expression_id == test_field_expression.id


def test_get_input_port_instance(ada_backend_mock_session: Session, test_component_instance):
    """Test retrieving an input port instance by ID."""
    created_port = input_port_instance_repository.create_input_port_instance(
        session=ada_backend_mock_session,
        component_instance_id=test_component_instance.id,
        name="test_port",
    )

    retrieved_port = input_port_instance_repository.get_input_port_instance(
        session=ada_backend_mock_session,
        input_port_instance_id=created_port.id,
    )

    assert retrieved_port is not None
    assert retrieved_port.id == created_port.id
    assert retrieved_port.name == "test_port"


def test_get_input_port_instances_for_component_instance(ada_backend_mock_session: Session, test_component_instance):
    """Test retrieving all input port instances for a component instance."""
    # Create multiple ports
    port1 = input_port_instance_repository.create_input_port_instance(
        session=ada_backend_mock_session,
        component_instance_id=test_component_instance.id,
        name="port1",
    )
    port2 = input_port_instance_repository.create_input_port_instance(
        session=ada_backend_mock_session,
        component_instance_id=test_component_instance.id,
        name="port2",
    )

    ports = input_port_instance_repository.get_input_port_instances_for_component_instance(
        session=ada_backend_mock_session,
        component_instance_id=test_component_instance.id,
    )

    assert len(ports) == 2
    port_ids = {p.id for p in ports}
    assert port1.id in port_ids
    assert port2.id in port_ids


def test_update_input_port_instance(ada_backend_mock_session: Session, test_component_instance):
    """Test updating an input port instance."""
    port = input_port_instance_repository.create_input_port_instance(
        session=ada_backend_mock_session,
        component_instance_id=test_component_instance.id,
        name="original_name",
    )

    updated_port = input_port_instance_repository.update_input_port_instance(
        session=ada_backend_mock_session,
        input_port_instance_id=port.id,
        name="updated_name",
        description="Updated description",
    )

    assert updated_port is not None
    assert updated_port.id == port.id
    assert updated_port.name == "updated_name"
    assert updated_port.description == "Updated description"


def test_delete_input_port_instance(ada_backend_mock_session: Session, test_component_instance):
    """Test deleting an input port instance."""
    port = input_port_instance_repository.create_input_port_instance(
        session=ada_backend_mock_session,
        component_instance_id=test_component_instance.id,
        name="to_delete",
    )

    result = input_port_instance_repository.delete_input_port_instance(
        session=ada_backend_mock_session,
        input_port_instance_id=port.id,
    )

    assert result is True

    # Verify it's deleted
    retrieved = input_port_instance_repository.get_input_port_instance(
        session=ada_backend_mock_session,
        input_port_instance_id=port.id,
    )
    assert retrieved is None


def test_update_clears_field_expression(
    ada_backend_mock_session: Session,
    test_component_instance,
    test_field_expression,
):
    """Test that explicitly setting field_expression_id to None clears it."""
    # Create a port with a field expression
    port = input_port_instance_repository.create_input_port_instance(
        session=ada_backend_mock_session,
        component_instance_id=test_component_instance.id,
        name="test_port",
        field_expression_id=test_field_expression.id,
    )

    assert port.field_expression_id == test_field_expression.id

    # Explicitly clear the field expression by setting it to None
    updated_port = input_port_instance_repository.update_input_port_instance(
        session=ada_backend_mock_session,
        input_port_instance_id=port.id,
        field_expression_id=None,
    )

    assert updated_port is not None
    assert updated_port.field_expression_id is None


def test_update_without_parameters_changes_nothing(
    ada_backend_mock_session: Session,
    test_component_instance,
    test_field_expression,
):
    """Test that calling update without parameters doesn't change anything."""
    # Create a port with values
    port = input_port_instance_repository.create_input_port_instance(
        session=ada_backend_mock_session,
        component_instance_id=test_component_instance.id,
        name="original_name",
        field_expression_id=test_field_expression.id,
        description="Original description",
    )

    original_name = port.name
    original_field_expr_id = port.field_expression_id
    original_description = port.description

    # Update without providing any parameters
    updated_port = input_port_instance_repository.update_input_port_instance(
        session=ada_backend_mock_session,
        input_port_instance_id=port.id,
    )

    assert updated_port is not None
    assert updated_port.name == original_name
    assert updated_port.field_expression_id == original_field_expr_id
    assert updated_port.description == original_description


def test_cascade_delete_component_instance(ada_backend_mock_session: Session, test_component_instance):
    """Test that deleting a component instance CASCADE deletes its input port instances."""
    # Create input port instances
    port1 = input_port_instance_repository.create_input_port_instance(
        session=ada_backend_mock_session,
        component_instance_id=test_component_instance.id,
        name="port1",
    )
    port2 = input_port_instance_repository.create_input_port_instance(
        session=ada_backend_mock_session,
        component_instance_id=test_component_instance.id,
        name="port2",
    )

    # Verify ports exist
    ports = input_port_instance_repository.get_input_port_instances_for_component_instance(
        session=ada_backend_mock_session,
        component_instance_id=test_component_instance.id,
    )
    assert len(ports) == 2

    # Delete the component instance
    ada_backend_mock_session.delete(test_component_instance)
    ada_backend_mock_session.commit()

    # Verify ports are CASCADE deleted
    port1_after = input_port_instance_repository.get_input_port_instance(
        session=ada_backend_mock_session,
        input_port_instance_id=port1.id,
    )
    port2_after = input_port_instance_repository.get_input_port_instance(
        session=ada_backend_mock_session,
        input_port_instance_id=port2.id,
    )
    assert port1_after is None
    assert port2_after is None


def test_set_null_on_field_expression_delete(
    ada_backend_mock_session: Session,
    test_component_instance,
    test_field_expression,
):
    """Test that deleting a field expression sets field_expression_id to NULL."""
    # Create port with field expression
    port = input_port_instance_repository.create_input_port_instance(
        session=ada_backend_mock_session,
        component_instance_id=test_component_instance.id,
        name="test_port",
        field_expression_id=test_field_expression.id,
    )

    assert port.field_expression_id == test_field_expression.id

    # Delete the field expression
    ada_backend_mock_session.delete(test_field_expression)
    ada_backend_mock_session.commit()

    # Refresh the port and verify field_expression_id is SET NULL
    ada_backend_mock_session.expire(port)
    retrieved_port = input_port_instance_repository.get_input_port_instance(
        session=ada_backend_mock_session,
        input_port_instance_id=port.id,
    )

    assert retrieved_port is not None
    assert retrieved_port.field_expression_id is None


def test_set_null_on_port_definition_delete(
    ada_backend_mock_session: Session,
    test_component_instance,
    test_port_definition,
):
    """Test that deleting a port definition sets port_definition_id to NULL."""
    # Create port with port definition
    port = input_port_instance_repository.create_input_port_instance(
        session=ada_backend_mock_session,
        component_instance_id=test_component_instance.id,
        name="test_port",
        port_definition_id=test_port_definition.id,
    )

    assert port.port_definition_id == test_port_definition.id

    # Delete the port definition
    ada_backend_mock_session.delete(test_port_definition)
    ada_backend_mock_session.commit()

    # Refresh the port and verify port_definition_id is SET NULL
    ada_backend_mock_session.expire(port)
    retrieved_port = input_port_instance_repository.get_input_port_instance(
        session=ada_backend_mock_session,
        input_port_instance_id=port.id,
    )

    assert retrieved_port is not None
    assert retrieved_port.port_definition_id is None


def test_unique_constraint_on_port_name(ada_backend_mock_session: Session, test_component_instance):
    """Test that unique constraint prevents duplicate port names for same instance."""
    input_port_instance_repository.create_input_port_instance(
        session=ada_backend_mock_session,
        component_instance_id=test_component_instance.id,
        name="duplicate_name",
    )

    # Attempting to create another port with the same name should raise an error
    with pytest.raises(Exception):  # SQLAlchemy will raise IntegrityError
        input_port_instance_repository.create_input_port_instance(
            session=ada_backend_mock_session,
            component_instance_id=test_component_instance.id,
            name="duplicate_name",
        )
