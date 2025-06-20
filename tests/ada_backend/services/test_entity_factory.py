from dataclasses import dataclass

import pytest
from pydantic import BaseModel

from ada_backend.services.entity_factory import (
    EntityFactory,
    AgentFactory,
    detect_and_convert_dataclasses,
    pydantic_processor,
    build_trace_manager_processor,
)
from engine.agent.agent import ToolDescription
from engine.trace.trace_manager import TraceManager
from tests.mocks.trace_manager import MockTraceManager


# --- Test classes ---
@dataclass
class TestDataclass:
    name: str
    value: int


class TestPydanticModel(BaseModel):
    name: str
    value: int


class TestEntity:
    def __init__(self, param1: str, param2: int, param3: float, param4: bool):
        self.param1 = param1
        self.param2 = param2
        self.param3 = param3
        self.param4 = param4


class TestEntityWithDataclass:
    def __init__(self, dataclass_param: TestDataclass, primitive_param: str):
        self.dataclass_param = dataclass_param
        self.primitive_param = primitive_param


class TestEntityWithPydantic:
    def __init__(self, pydantic_param: TestPydanticModel, primitive_param: int):
        self.pydantic_param = pydantic_param
        self.primitive_param = primitive_param


class TestAgent:
    def __init__(self, tool_description: ToolDescription, trace_manager: TraceManager):
        self.tool_description = tool_description
        self.trace_manager = trace_manager


# --- Tests ---
def test_entity_factory_basic_instantiation():
    factory = EntityFactory(TestEntity)
    instance = factory(param1="test", param2=42, param3=3.14, param4=True)
    assert isinstance(instance, TestEntity)
    assert instance.param1 == "test"
    assert instance.param2 == 42
    assert instance.param3 == 3.14
    assert instance.param4 is True


def test_entity_factory_missing_params():
    factory = EntityFactory(TestEntity)
    with pytest.raises(TypeError):
        factory(param1="test", param2=42)  # Missing param3 and param4


def test_entity_factory_with_processors():
    factory = EntityFactory(
        TestEntityWithDataclass,
        parameter_processors=[detect_and_convert_dataclasses],
    )
    instance = factory(
        dataclass_param={"name": "test_dataclass", "value": 42},
        primitive_param="primitive_value",
    )
    assert isinstance(instance, TestEntityWithDataclass)
    assert isinstance(instance.dataclass_param, TestDataclass)
    assert instance.dataclass_param.name == "test_dataclass"
    assert instance.dataclass_param.value == 42
    assert instance.primitive_param == "primitive_value"


def test_agent_factory_instantiation():
    mock_trace_manager = MockTraceManager(project_name="test_project")
    factory = AgentFactory(
        entity_class=TestAgent,
        trace_manager=mock_trace_manager,
        parameter_processors=[],
    )

    tool_description = ToolDescription(
        name="mock_tool",
        description="A mock tool description",
        tool_properties={"key": {"type": "string", "description": "A test key"}},
        required_tool_properties=["key"],
    )

    instance = factory(tool_description=tool_description)
    assert isinstance(instance, TestAgent)
    assert instance.tool_description == tool_description
    assert instance.trace_manager == mock_trace_manager


def test_agent_factory_missing_tool_description():
    mock_trace_manager = MockTraceManager(project_name="test_project")
    factory = AgentFactory(
        entity_class=TestAgent,
        trace_manager=mock_trace_manager,
        parameter_processors=[],
    )

    with pytest.raises(ValueError, match="Tool description must be a ToolDescription object."):
        factory()


def test_pydantic_processor():
    factory = EntityFactory(
        TestEntityWithPydantic,
        parameter_processors=[pydantic_processor],
    )
    instance = factory(
        pydantic_param={"name": "pydantic_name", "value": 99},
        primitive_param=100,
    )
    assert isinstance(instance, TestEntityWithPydantic)
    assert isinstance(instance.pydantic_param, TestPydanticModel)
    assert instance.pydantic_param.name == "pydantic_name"
    assert instance.pydantic_param.value == 99
    assert instance.primitive_param == 100


def test_combined_processor_usage():
    factory = EntityFactory(
        TestEntityWithDataclass,
        parameter_processors=[detect_and_convert_dataclasses, pydantic_processor],
    )

    instance = factory(
        dataclass_param={"name": "dc_test", "value": 1},
        primitive_param="dc_value",
    )
    assert isinstance(instance, TestEntityWithDataclass)
    assert isinstance(instance.dataclass_param, TestDataclass)
    assert instance.dataclass_param.name == "dc_test"
    assert instance.primitive_param == "dc_value"


def test_trace_manager_processor():
    mock_trace_manager = MockTraceManager(project_name="test_project")
    factory = EntityFactory(
        TestAgent,
        parameter_processors=[build_trace_manager_processor(mock_trace_manager)],
    )
    tool_description = ToolDescription(
        name="tool_name",
        description="A tool description",
        tool_properties={"param": {"type": "integer", "description": "A number"}},
        required_tool_properties=["param"],
    )

    instance = factory(tool_description=tool_description)
    assert instance.trace_manager == mock_trace_manager
    assert instance.tool_description == tool_description


def test_agent_factory_invalid_tool_description():
    mock_trace_manager = MockTraceManager(project_name="test_project")
    factory = AgentFactory(
        entity_class=TestAgent,
        trace_manager=mock_trace_manager,
        parameter_processors=[],
    )

    invalid_tool_description = {
        "name": "mock_tool",
        "description": "A mock tool description",
        "tool_properties": {"key": {"type": "string", "description": "A test key"}},
        "required_tool_properties": ["key"],
    }

    with pytest.raises(ValueError, match="Tool description must be a ToolDescription object."):
        factory(tool_description=invalid_tool_description)
