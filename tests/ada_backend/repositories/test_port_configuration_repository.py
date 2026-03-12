"""Tests for the tool input configuration repository."""

import uuid

import pytest
from sqlalchemy.orm import Session

from ada_backend.database import models as db
from ada_backend.repositories import port_configuration_repository

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


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


@pytest.fixture
def test_input_port_instance(ada_backend_mock_session: Session, test_component_instance, test_port_definition):
    """An InputPortInstance that backs a catalogue-defined port."""
    port_instance = db.InputPortInstance(
        id=uuid.uuid4(),
        component_instance_id=test_component_instance.id,
        name=test_port_definition.name,
        port_definition_id=test_port_definition.id,
        type=db.PortType.INPUT,
    )
    ada_backend_mock_session.add(port_instance)
    ada_backend_mock_session.commit()
    return port_instance


@pytest.fixture
def test_dynamic_input_port_instance(ada_backend_mock_session: Session, test_component_instance):
    """An InputPortInstance for a dynamic (custom) port with no PortDefinition."""
    port_instance = db.InputPortInstance(
        id=uuid.uuid4(),
        component_instance_id=test_component_instance.id,
        name="custom_port",
        port_definition_id=None,
        type=db.PortType.INPUT,
        description="A dynamic custom port",
    )
    ada_backend_mock_session.add(port_instance)
    ada_backend_mock_session.commit()
    return port_instance


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_insert_tool_input_configuration(ada_backend_mock_session: Session, test_input_port_instance):
    config = port_configuration_repository.insert_tool_input_configuration(
        session=ada_backend_mock_session,
        input_port_instance_id=test_input_port_instance.id,
        setup_mode=db.PortSetupMode.USER_SET,
        ai_name_override="custom_name",
        ai_description_override="Custom description",
    )

    assert isinstance(config, db.ToolInputConfiguration)
    assert config.id is not None
    assert config.input_port_instance_id == test_input_port_instance.id
    assert config.setup_mode == db.PortSetupMode.USER_SET
    assert config.ai_name_override == "custom_name"
    assert config.ai_description_override == "Custom description"


def test_get_tool_input_configurations(
    ada_backend_mock_session: Session,
    test_component_instance,
    test_input_port_instance,
    test_dynamic_input_port_instance,
):
    config1 = port_configuration_repository.insert_tool_input_configuration(
        session=ada_backend_mock_session,
        input_port_instance_id=test_input_port_instance.id,
        setup_mode=db.PortSetupMode.AI_FILLED,
    )
    config2 = port_configuration_repository.insert_tool_input_configuration(
        session=ada_backend_mock_session,
        input_port_instance_id=test_dynamic_input_port_instance.id,
        setup_mode=db.PortSetupMode.AI_FILLED,
        custom_parameter_type=db.JsonSchemaType.STRING,
    )

    configs = port_configuration_repository.get_tool_input_configurations(
        ada_backend_mock_session, test_component_instance.id
    )

    assert len(configs) == 2
    assert config1.id in [c.id for c in configs]
    assert config2.id in [c.id for c in configs]


def test_update_tool_input_configuration(ada_backend_mock_session: Session, test_input_port_instance):
    config = port_configuration_repository.insert_tool_input_configuration(
        session=ada_backend_mock_session,
        input_port_instance_id=test_input_port_instance.id,
        setup_mode=db.PortSetupMode.USER_SET,
        ai_name_override="original_name",
    )

    updated = port_configuration_repository.update_tool_input_configuration(
        session=ada_backend_mock_session,
        config_id=config.id,
        ai_name_override="updated_name",
        ai_description_override="Updated description",
    )

    assert updated is not None
    assert updated.ai_name_override == "updated_name"
    assert updated.ai_description_override == "Updated description"
    assert updated.setup_mode == db.PortSetupMode.USER_SET  # unchanged


def test_delete_tool_input_configuration(ada_backend_mock_session: Session, test_input_port_instance):
    config = port_configuration_repository.insert_tool_input_configuration(
        session=ada_backend_mock_session,
        input_port_instance_id=test_input_port_instance.id,
        setup_mode=db.PortSetupMode.AI_FILLED,
    )

    success = port_configuration_repository.delete_tool_input_configuration(ada_backend_mock_session, config.id)
    assert success is True

    retrieved = port_configuration_repository.get_tool_input_configuration_by_id(ada_backend_mock_session, config.id)
    assert retrieved is None


def test_get_tool_input_configuration_by_input_port_instance(
    ada_backend_mock_session: Session, test_input_port_instance
):
    config = port_configuration_repository.insert_tool_input_configuration(
        session=ada_backend_mock_session,
        input_port_instance_id=test_input_port_instance.id,
        setup_mode=db.PortSetupMode.AI_FILLED,
    )

    retrieved = port_configuration_repository.get_tool_input_configuration_by_input_port_instance(
        ada_backend_mock_session, test_input_port_instance.id
    )

    assert retrieved is not None
    assert retrieved.id == config.id


def test_upsert_tool_input_configurations_insert(
    ada_backend_mock_session: Session,
    test_component_instance,
    test_input_port_instance,
    test_dynamic_input_port_instance,
):
    configs_data = [
        {
            "input_port_instance_id": test_input_port_instance.id,
            "setup_mode": "ai_filled",
            "ai_name_override": "param1",
        },
        {
            "input_port_instance_id": test_dynamic_input_port_instance.id,
            "setup_mode": "ai_filled",
            "custom_parameter_type": "string",
        },
    ]

    result = port_configuration_repository.upsert_tool_input_configurations(
        ada_backend_mock_session, test_component_instance.id, configs_data
    )

    assert len(result) == 2
    assert all(isinstance(c, db.ToolInputConfiguration) for c in result)


def test_upsert_tool_input_configurations_update_by_id(
    ada_backend_mock_session: Session,
    test_component_instance,
    test_input_port_instance,
):
    config = port_configuration_repository.insert_tool_input_configuration(
        session=ada_backend_mock_session,
        input_port_instance_id=test_input_port_instance.id,
        setup_mode=db.PortSetupMode.AI_FILLED,
        ai_name_override="original",
    )

    result = port_configuration_repository.upsert_tool_input_configurations(
        ada_backend_mock_session,
        test_component_instance.id,
        [{"id": config.id, "setup_mode": "user_set", "ai_name_override": "updated"}],
    )

    assert len(result) == 1
    assert result[0].id == config.id
    assert result[0].setup_mode == db.PortSetupMode.USER_SET
    assert result[0].ai_name_override == "updated"


def test_upsert_tool_input_configurations_update_by_port_instance(
    ada_backend_mock_session: Session,
    test_component_instance,
    test_input_port_instance,
):
    """Upsert by input_port_instance_id should update an existing config."""
    config = port_configuration_repository.insert_tool_input_configuration(
        session=ada_backend_mock_session,
        input_port_instance_id=test_input_port_instance.id,
        setup_mode=db.PortSetupMode.AI_FILLED,
    )

    result = port_configuration_repository.upsert_tool_input_configurations(
        ada_backend_mock_session,
        test_component_instance.id,
        [
            {
                "input_port_instance_id": test_input_port_instance.id,
                "setup_mode": "user_set",
                "ai_description_override": "New description",
            }
        ],
    )

    assert len(result) == 1
    assert result[0].id == config.id  # same row, not a new one
    assert result[0].setup_mode == db.PortSetupMode.USER_SET
    assert result[0].ai_description_override == "New description"
