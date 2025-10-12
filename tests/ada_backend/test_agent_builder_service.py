"""Test for agent_builder_service resolution_phase filtering."""
import uuid
from unittest.mock import MagicMock, patch

from ada_backend.database.models import (
    BasicParameter,
    ComponentInstance,
    ParameterResolutionPhase,
    ComponentParameterDefinition,
    ParameterType,
)
from ada_backend.services.agent_builder_service import get_component_params


@patch('ada_backend.services.agent_builder_service.get_component_basic_parameters')
@patch('ada_backend.services.agent_builder_service.get_component_instance_by_id')
def test_get_component_params_filters_runtime_parameters(mock_get_instance, mock_get_params):
    """Test that runtime parameters are excluded from constructor params."""
    # Setup mock session
    session = MagicMock()
    component_instance_id = uuid.uuid4()
    component_id = uuid.uuid4()
    project_id = uuid.uuid4()

    # Create mock component instance
    component_instance = MagicMock(spec=ComponentInstance)
    component_instance.component_id = component_id

    # Create mock parameter definitions
    param_def_1 = MagicMock(spec=ComponentParameterDefinition)
    param_def_1.id = uuid.uuid4()
    param_def_1.name = "model_name"
    param_def_1.type = ParameterType.STRING

    param_def_2 = MagicMock(spec=ComponentParameterDefinition)
    param_def_2.id = uuid.uuid4()
    param_def_2.name = "system_prompt"
    param_def_2.type = ParameterType.STRING

    # Create mock parameters - one constructor, one runtime
    constructor_param = MagicMock(spec=BasicParameter)
    constructor_param.parameter_definition = param_def_1
    constructor_param.resolution_phase = ParameterResolutionPhase.CONSTRUCTOR
    constructor_param.value = "gpt-4"
    constructor_param.organization_secret_id = None
    constructor_param.order = None
    constructor_param.get_value.return_value = "gpt-4"

    runtime_param = MagicMock(spec=BasicParameter)
    runtime_param.parameter_definition = param_def_2
    runtime_param.resolution_phase = ParameterResolutionPhase.RUNTIME
    runtime_param.value = "{{@input.message}}"
    runtime_param.organization_secret_id = None
    runtime_param.order = None
    runtime_param.get_value.return_value = "{{@input.message}}"

    # Set up mocks
    mock_get_instance.return_value = component_instance
    mock_get_params.return_value = [constructor_param, runtime_param]

    # Call the function
    params = get_component_params(session, component_instance_id, project_id)

    # Assertions
    assert "model_name" in params
    assert params["model_name"] == "gpt-4"
    assert "system_prompt" not in params  # Runtime parameter should be excluded


@patch('ada_backend.services.agent_builder_service.get_component_basic_parameters')
@patch('ada_backend.services.agent_builder_service.get_component_instance_by_id')
def test_get_component_params_includes_constructor_parameters(mock_get_instance, mock_get_params):
    """Test that constructor parameters are included."""
    # Setup mock session
    session = MagicMock()
    component_instance_id = uuid.uuid4()
    component_id = uuid.uuid4()
    project_id = uuid.uuid4()

    # Create mock component instance
    component_instance = MagicMock(spec=ComponentInstance)
    component_instance.component_id = component_id

    # Create mock parameter definitions
    param_def_1 = MagicMock(spec=ComponentParameterDefinition)
    param_def_1.id = uuid.uuid4()
    param_def_1.name = "api_key"
    param_def_1.type = ParameterType.STRING

    param_def_2 = MagicMock(spec=ComponentParameterDefinition)
    param_def_2.id = uuid.uuid4()
    param_def_2.name = "temperature"
    param_def_2.type = ParameterType.FLOAT

    # Create mock parameters - both constructor
    api_param = MagicMock(spec=BasicParameter)
    api_param.parameter_definition = param_def_1
    api_param.resolution_phase = ParameterResolutionPhase.CONSTRUCTOR
    api_param.value = "secret-key"
    api_param.organization_secret_id = None
    api_param.order = None
    api_param.get_value.return_value = "secret-key"

    temp_param = MagicMock(spec=BasicParameter)
    temp_param.parameter_definition = param_def_2
    temp_param.resolution_phase = ParameterResolutionPhase.CONSTRUCTOR
    temp_param.value = "0.7"
    temp_param.organization_secret_id = None
    temp_param.order = None
    temp_param.get_value.return_value = 0.7

    # Set up mocks
    mock_get_instance.return_value = component_instance
    mock_get_params.return_value = [api_param, temp_param]

    # Call the function
    params = get_component_params(session, component_instance_id, project_id)

    # Assertions
    assert "api_key" in params
    assert params["api_key"] == "secret-key"
    assert "temperature" in params
    assert params["temperature"] == 0.7