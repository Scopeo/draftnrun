"""Tests for input_port_instance_repository functions."""

import uuid

from ada_backend.database import models as db
from ada_backend.database.setup_db import get_db_session
from ada_backend.repositories import input_port_instance_repository


def _create_test_component_instance(session):
    """Create a test component instance."""
    unique_id = uuid.uuid4()
    component = db.Component(
        id=uuid.uuid4(),
        name=f"Test Component {unique_id}",
        description="Test component for port instances",
    )
    session.add(component)
    session.flush()

    component_version = db.ComponentVersion(
        id=uuid.uuid4(),
        component_id=component.id,
        version_tag="1.0.0",
    )
    session.add(component_version)
    session.flush()

    component_instance = db.ComponentInstance(
        id=uuid.uuid4(),
        component_version_id=component_version.id,
        name="Test Instance",
    )
    session.add(component_instance)
    session.commit()

    return component_instance


def _create_test_port_definition(session, component_instance):
    """Create a test port definition."""
    port_def = db.PortDefinition(
        id=uuid.uuid4(),
        component_version_id=component_instance.component_version_id,
        name="test_port",
        port_type=db.PortType.INPUT,
        is_canonical=False,
    )
    session.add(port_def)
    session.commit()
    return port_def


def _create_test_field_expression(session):
    """Create a test field expression."""
    field_expr = db.FieldExpression(
        id=uuid.uuid4(),
        expression_json={"type": "literal", "value": "test"},
    )
    session.add(field_expr)
    session.commit()
    return field_expr


def test_create_input_port_instance():
    """Test creating an input port instance."""
    with get_db_session() as session:
        test_component_instance = _create_test_component_instance(session)

        port = input_port_instance_repository.create_input_port_instance(
            session=session,
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


def test_create_input_port_instance_with_references():
    """Test creating an input port instance with port definition and field expression."""
    with get_db_session() as session:
        test_component_instance = _create_test_component_instance(session)
        test_port_definition = _create_test_port_definition(session, test_component_instance)
        test_field_expression = _create_test_field_expression(session)

        port = input_port_instance_repository.create_input_port_instance(
            session=session,
            component_instance_id=test_component_instance.id,
            name="test_input_port",
            port_definition_id=test_port_definition.id,
            field_expression_id=test_field_expression.id,
            description="Port with references",
        )

        assert port.id is not None
        assert port.port_definition_id == test_port_definition.id
        assert port.field_expression_id == test_field_expression.id


def test_get_input_port_instance():
    """Test retrieving an input port instance by ID."""
    with get_db_session() as session:
        test_component_instance = _create_test_component_instance(session)

        created_port = input_port_instance_repository.create_input_port_instance(
            session=session,
            component_instance_id=test_component_instance.id,
            name="test_port",
        )

        retrieved_port = input_port_instance_repository.get_input_port_instance(
            session=session,
            input_port_instance_id=created_port.id,
        )

        assert retrieved_port is not None
        assert retrieved_port.id == created_port.id
        assert retrieved_port.name == "test_port"


def test_get_input_port_instances_for_component_instance():
    """Test retrieving all input port instances for a component instance."""
    with get_db_session() as session:
        test_component_instance = _create_test_component_instance(session)

        # Create multiple ports
        port1 = input_port_instance_repository.create_input_port_instance(
            session=session,
            component_instance_id=test_component_instance.id,
            name="port1",
        )
        port2 = input_port_instance_repository.create_input_port_instance(
            session=session,
            component_instance_id=test_component_instance.id,
            name="port2",
        )

        ports = input_port_instance_repository.get_input_port_instances_for_component_instance(
            session=session,
            component_instance_id=test_component_instance.id,
        )

        assert len(ports) == 2
        port_ids = {p.id for p in ports}
        assert port1.id in port_ids
        assert port2.id in port_ids


def test_update_input_port_instance():
    """Test updating an input port instance."""
    with get_db_session() as session:
        test_component_instance = _create_test_component_instance(session)

        port = input_port_instance_repository.create_input_port_instance(
            session=session,
            component_instance_id=test_component_instance.id,
            name="original_name",
        )

        updated_port = input_port_instance_repository.update_input_port_instance(
            session=session,
            input_port_instance_id=port.id,
            name="updated_name",
            description="Updated description",
        )

        assert updated_port is not None
        assert updated_port.id == port.id
        assert updated_port.name == "updated_name"
        assert updated_port.description == "Updated description"


def test_delete_input_port_instance():
    """Test deleting an input port instance."""
    with get_db_session() as session:
        test_component_instance = _create_test_component_instance(session)

        port = input_port_instance_repository.create_input_port_instance(
            session=session,
            component_instance_id=test_component_instance.id,
            name="to_delete",
        )

        result = input_port_instance_repository.delete_input_port_instance(
            session=session,
            input_port_instance_id=port.id,
        )

        assert result is True

        # Verify it's deleted
        retrieved = input_port_instance_repository.get_input_port_instance(
            session=session,
            input_port_instance_id=port.id,
        )
        assert retrieved is None


def test_update_clears_field_expression():
    """Test that explicitly setting field_expression_id to None clears it."""
    with get_db_session() as session:
        test_component_instance = _create_test_component_instance(session)
        test_field_expression = _create_test_field_expression(session)

        # Create a port with a field expression
        port = input_port_instance_repository.create_input_port_instance(
            session=session,
            component_instance_id=test_component_instance.id,
            name="test_port",
            field_expression_id=test_field_expression.id,
        )

        assert port.field_expression_id == test_field_expression.id

        # Explicitly clear the field expression by setting it to None
        updated_port = input_port_instance_repository.update_input_port_instance(
            session=session,
            input_port_instance_id=port.id,
            field_expression_id=None,
        )

        assert updated_port is not None
        assert updated_port.field_expression_id is None


def test_update_without_parameters_changes_nothing():
    """Test that calling update without parameters doesn't change anything."""
    with get_db_session() as session:
        test_component_instance = _create_test_component_instance(session)
        test_field_expression = _create_test_field_expression(session)

        # Create a port with values
        port = input_port_instance_repository.create_input_port_instance(
            session=session,
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
            session=session,
            input_port_instance_id=port.id,
        )

        assert updated_port is not None
        assert updated_port.name == original_name
        assert updated_port.field_expression_id == original_field_expr_id
        assert updated_port.description == original_description


def test_cascade_delete_component_instance():
    """Test that deleting a component instance CASCADE deletes its input port instances."""
    with get_db_session() as session:
        test_component_instance = _create_test_component_instance(session)

        # Create input port instances
        port1 = input_port_instance_repository.create_input_port_instance(
            session=session,
            component_instance_id=test_component_instance.id,
            name="port1",
        )
        port2 = input_port_instance_repository.create_input_port_instance(
            session=session,
            component_instance_id=test_component_instance.id,
            name="port2",
        )

        # Verify ports exist
        ports = input_port_instance_repository.get_input_port_instances_for_component_instance(
            session=session,
            component_instance_id=test_component_instance.id,
        )
        assert len(ports) == 2

        # Delete the component instance
        session.delete(test_component_instance)
        session.commit()

        # Verify ports are CASCADE deleted
        port1_after = input_port_instance_repository.get_input_port_instance(
            session=session,
            input_port_instance_id=port1.id,
        )
        port2_after = input_port_instance_repository.get_input_port_instance(
            session=session,
            input_port_instance_id=port2.id,
        )
        assert port1_after is None
        assert port2_after is None


def test_set_null_on_field_expression_delete():
    """Test that deleting a field expression sets field_expression_id to NULL."""
    with get_db_session() as session:
        test_component_instance = _create_test_component_instance(session)
        test_field_expression = _create_test_field_expression(session)

        # Create port with field expression
        port = input_port_instance_repository.create_input_port_instance(
            session=session,
            component_instance_id=test_component_instance.id,
            name="test_port",
            field_expression_id=test_field_expression.id,
        )

        assert port.field_expression_id == test_field_expression.id

        # Delete the field expression
        session.delete(test_field_expression)
        session.commit()

        # Refresh the port and verify field_expression_id is SET NULL
        session.expire(port)
        retrieved_port = input_port_instance_repository.get_input_port_instance(
            session=session,
            input_port_instance_id=port.id,
        )

        assert retrieved_port is not None
        assert retrieved_port.field_expression_id is None


def test_set_null_on_port_definition_delete():
    """Test that deleting a port definition sets port_definition_id to NULL."""
    with get_db_session() as session:
        test_component_instance = _create_test_component_instance(session)
        test_port_definition = _create_test_port_definition(session, test_component_instance)

        # Create port with port definition
        port = input_port_instance_repository.create_input_port_instance(
            session=session,
            component_instance_id=test_component_instance.id,
            name="test_port",
            port_definition_id=test_port_definition.id,
        )

        assert port.port_definition_id == test_port_definition.id

        # Delete the port definition
        session.delete(test_port_definition)
        session.commit()

        # Refresh the port and verify port_definition_id is SET NULL
        session.expire(port)
        retrieved_port = input_port_instance_repository.get_input_port_instance(
            session=session,
            input_port_instance_id=port.id,
        )

        assert retrieved_port is not None
        assert retrieved_port.port_definition_id is None


def test_unique_constraint_on_port_name():
    """Test that unique constraint prevents duplicate port names for same instance."""
    with get_db_session() as session:
        test_component_instance = _create_test_component_instance(session)

        input_port_instance_repository.create_input_port_instance(
            session=session,
            component_instance_id=test_component_instance.id,
            name="duplicate_name",
        )

        # Attempting to create another port with the same name should raise an error
        try:
            input_port_instance_repository.create_input_port_instance(
                session=session,
                component_instance_id=test_component_instance.id,
                name="duplicate_name",
            )
            # If we get here, the test should fail
            assert False, "Expected IntegrityError was not raised"
        except Exception as e:
            # Verify it's the right kind of error
            assert "duplicate key value" in str(e) or "IntegrityError" in str(type(e))
            # Rollback to clean up the failed transaction
            session.rollback()
