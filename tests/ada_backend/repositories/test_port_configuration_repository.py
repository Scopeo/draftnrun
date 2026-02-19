"""
Tests for port configuration repository functions.
"""

import uuid

import pytest
from sqlalchemy.orm import Session

from ada_backend.database import models as db
from ada_backend.repositories import port_configuration_repository


@pytest.fixture
def test_component_version(ada_backend_mock_session: Session):
    component = db.Component(
        id=uuid.uuid4(),
        name="Test Tool Component",
        base_component="tool",
    )
    ada_backend_mock_session.add(component)
    ada_backend_mock_session.flush()

    component_version = db.ComponentVersion(
        id=uuid.uuid4(),
        component_id=component.id,
        version_tag="1.0.0",
    )
    ada_backend_mock_session.add(component_version)
    ada_backend_mock_session.flush()

    return component_version


@pytest.fixture
def test_component_instance(ada_backend_mock_session: Session, test_component_version):
    instance = db.ComponentInstance(
        id=uuid.uuid4(),
        component_version_id=test_component_version.id,
        name="Test Tool Instance",
        ref="test_tool",
    )
    ada_backend_mock_session.add(instance)
    ada_backend_mock_session.commit()

    return instance


@pytest.fixture
def test_port_definition(ada_backend_mock_session: Session, test_component_version):
    """Create a test port definition."""
    port_def = db.PortDefinition(
        id=uuid.uuid4(),
        component_version_id=test_component_version.id,
        name="input_param",
        port_type=db.PortType.INPUT,
        is_canonical=True,
        description="Test input parameter",
        parameter_type=db.ParameterType.STRING,
    )
    ada_backend_mock_session.add(port_def)
    ada_backend_mock_session.commit()

    return port_def


def test_insert_port_configuration(ada_backend_mock_session: Session, test_component_instance, test_port_definition):
    # Create with field expression
    expression_json = {"type": "literal", "value": "test_value"}

    config = port_configuration_repository.insert_port_configuration(
        session=ada_backend_mock_session,
        component_instance_id=test_component_instance.id,
        port_definition_id=test_port_definition.id,
        setup_mode="user_set",
        expression_json=expression_json,
        ai_name_override="custom_name",
        ai_description_override="Custom description",
    )

    # Verify it's a ToolInputConfiguration instance
    assert isinstance(config, db.ToolInputConfiguration)
    assert config.id is not None
    assert config.component_instance_id == test_component_instance.id
    assert config.port_definition_id == test_port_definition.id
    assert config.setup_mode == db.PortSetupMode.USER_SET
    assert config.field_expression_id is not None
    assert config.ai_name_override == "custom_name"
    assert config.ai_description_override == "Custom description"


def test_get_port_configurations(ada_backend_mock_session: Session, test_component_instance, test_port_definition):
    """Test retrieving all port configurations for a component instance."""
    # Insert multiple configurations
    config1 = port_configuration_repository.insert_port_configuration(
        session=ada_backend_mock_session,
        component_instance_id=test_component_instance.id,
        port_definition_id=test_port_definition.id,
        setup_mode="ai_filled",
    )

    config2 = port_configuration_repository.insert_port_configuration(
        session=ada_backend_mock_session,
        component_instance_id=test_component_instance.id,
        setup_mode="ai_filled",
        custom_port_name="custom_port",
        custom_port_description="Custom port",
        custom_parameter_type="string",
    )

    # Retrieve configurations
    configs = port_configuration_repository.get_port_configurations(
        ada_backend_mock_session, test_component_instance.id
    )

    assert len(configs) == 2
    assert config1.id in [c.id for c in configs]
    assert config2.id in [c.id for c in configs]


def test_update_port_configuration(ada_backend_mock_session: Session, test_component_instance, test_port_definition):
    """Test updating an existing port configuration."""
    # Insert a configuration
    expression_json = {"type": "literal", "value": "original_value"}
    config = port_configuration_repository.insert_port_configuration(
        session=ada_backend_mock_session,
        component_instance_id=test_component_instance.id,
        port_definition_id=test_port_definition.id,
        setup_mode="user_set",
        expression_json=expression_json,
        ai_name_override="original_name",
    )

    # Update the configuration with new expression
    new_expression_json = {"type": "literal", "value": "updated_value"}
    updated_config = port_configuration_repository.update_port_configuration(
        session=ada_backend_mock_session,
        config_id=config.id,
        expression_json=new_expression_json,
        ai_name_override="updated_name",
        ai_description_override="Updated description",
    )

    assert updated_config is not None
    assert updated_config.ai_name_override == "updated_name"
    assert updated_config.ai_description_override == "Updated description"
    # Verify expression was updated
    assert updated_config.field_expression is not None
    assert updated_config.field_expression.expression_json["value"] == "updated_value"


def test_delete_port_configuration(ada_backend_mock_session: Session, test_component_instance, test_port_definition):
    """Test deleting a port configuration."""
    # Insert a configuration
    config = port_configuration_repository.insert_port_configuration(
        session=ada_backend_mock_session,
        component_instance_id=test_component_instance.id,
        port_definition_id=test_port_definition.id,
        setup_mode="ai_filled",
    )

    # Delete the configuration
    success = port_configuration_repository.delete_port_configuration(ada_backend_mock_session, config.id)

    assert success is True

    # Verify it's deleted
    retrieved_config = port_configuration_repository.get_port_configuration_by_id(ada_backend_mock_session, config.id)
    assert retrieved_config is None


def test_upsert_port_configurations(ada_backend_mock_session: Session, test_component_instance, test_port_definition):
    """Test upserting multiple port configurations."""
    # First upsert - insert new configurations
    configs_data = [
        {
            "port_definition_id": test_port_definition.id,
            "setup_mode": "ai_filled",
            "ai_name_override": "param1",
        },
        {
            "setup_mode": "ai_filled",
            "custom_port_name": "custom1",
            "custom_port_description": "Custom port 1",
            "custom_parameter_type": "string",
        },
    ]

    result_configs = port_configuration_repository.upsert_port_configurations(
        ada_backend_mock_session, test_component_instance.id, configs_data
    )

    assert len(result_configs) == 2

    # Second upsert - update existing + add new
    config_id_to_update = result_configs[0].id

    # Should have 3 total (2 from first upsert + 1 new from second)
    all_configs = port_configuration_repository.get_port_configurations(
        ada_backend_mock_session, test_component_instance.id
    )
    assert len(all_configs) == 3

    # Check the updated config
    updated_config = port_configuration_repository.get_port_configuration_by_id(
        ada_backend_mock_session, config_id_to_update
    )
    assert updated_config.setup_mode == db.PortSetupMode.USER_SET
    assert updated_config.field_expression_id is not None


def test_get_port_configuration_by_port_definition(
    ada_backend_mock_session: Session, test_component_instance, test_port_definition
):
    """Test retrieving a port configuration by port definition."""
    # Insert a configuration
    config = port_configuration_repository.insert_port_configuration(
        session=ada_backend_mock_session,
        component_instance_id=test_component_instance.id,
        port_definition_id=test_port_definition.id,
        setup_mode="ai_filled",
    )

    # Retrieve by port definition
    retrieved_config = port_configuration_repository.get_port_configuration_by_port_definition(
        ada_backend_mock_session, test_component_instance.id, test_port_definition.id
    )

    assert retrieved_config is not None
    assert retrieved_config.id == config.id


def test_get_port_configuration_by_custom_name(ada_backend_mock_session: Session, test_component_instance):
    """Test retrieving a port configuration by custom name."""
    # Insert a custom port configuration
    config = port_configuration_repository.insert_port_configuration(
        session=ada_backend_mock_session,
        component_instance_id=test_component_instance.id,
        setup_mode="ai_filled",
        custom_port_name="my_custom_port",
        custom_port_description="My custom port",
        custom_parameter_type="string",
    )

    # Retrieve by custom name
    retrieved_config = port_configuration_repository.get_port_configuration_by_custom_name(
        ada_backend_mock_session, test_component_instance.id, "my_custom_port"
    )

    assert retrieved_config is not None
    assert retrieved_config.id == config.id
    assert retrieved_config.custom_port_name == "my_custom_port"
