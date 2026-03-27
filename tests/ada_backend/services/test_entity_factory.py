import uuid
from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import pytest
from pydantic import BaseModel

from ada_backend.context import set_current_project_id
from ada_backend.services.entity_factory import (
    AgentFactory,
    EntityFactory,
    build_project_reference_processor,
    build_trace_manager_processor,
    detect_and_convert_dataclasses,
    get_llm_provider_and_model,
    pydantic_processor,
)
from engine.components.types import ToolDescription
from engine.trace.trace_context import get_trace_manager
from engine.trace.trace_manager import TraceManager


# --- Mock classes for testing ---
@dataclass
class MockDataclass:
    name: str
    value: int


class MockPydanticModel(BaseModel):
    name: str
    value: int


class MockEntity:
    def __init__(self, param1: str, param2: int, param3: float, param4: bool):
        self.param1 = param1
        self.param2 = param2
        self.param3 = param3
        self.param4 = param4


class MockEntityWithDataclass:
    def __init__(self, dataclass_param: MockDataclass, primitive_param: str):
        self.dataclass_param = dataclass_param
        self.primitive_param = primitive_param


class MockEntityWithPydantic:
    def __init__(self, pydantic_param: MockPydanticModel, primitive_param: int):
        self.pydantic_param = pydantic_param
        self.primitive_param = primitive_param


class MockAgent:
    def __init__(self, tool_description: ToolDescription, trace_manager: TraceManager):
        self.tool_description = tool_description
        self.trace_manager = trace_manager


# --- Tests ---
@pytest.mark.asyncio
async def test_entity_factory_basic_instantiation():
    factory = EntityFactory(MockEntity)
    instance = await factory(param1="test", param2=42, param3=3.14, param4=True)
    assert isinstance(instance, MockEntity)
    assert instance.param1 == "test"
    assert instance.param2 == 42
    assert instance.param3 == 3.14
    assert instance.param4 is True


@pytest.mark.asyncio
async def test_entity_factory_missing_params():
    factory = EntityFactory(MockEntity)
    with pytest.raises(TypeError):
        await factory(param1="test", param2=42)  # Missing param3 and param4


@pytest.mark.asyncio
async def test_entity_factory_with_processors():
    factory = EntityFactory(
        MockEntityWithDataclass,
        parameter_processors=[detect_and_convert_dataclasses],
    )
    instance = await factory(
        dataclass_param={"name": "test_dataclass", "value": 42},
        primitive_param="primitive_value",
    )
    assert isinstance(instance, MockEntityWithDataclass)
    assert isinstance(instance.dataclass_param, MockDataclass)
    assert instance.dataclass_param.name == "test_dataclass"
    assert instance.dataclass_param.value == 42
    assert instance.primitive_param == "primitive_value"


@pytest.mark.asyncio
async def test_agent_factory_instantiation():
    factory = AgentFactory(
        entity_class=MockAgent,
        parameter_processors=[],
    )

    tool_description = ToolDescription(
        name="mock_tool",
        description="A mock tool description",
        tool_properties={"key": {"type": "string", "description": "A test key"}},
        required_tool_properties=["key"],
    )

    instance = await factory(tool_description=tool_description)
    assert isinstance(instance, MockAgent)
    assert instance.tool_description == tool_description
    assert instance.trace_manager == get_trace_manager()


@pytest.mark.asyncio
async def test_agent_factory_missing_tool_description():
    factory = AgentFactory(
        entity_class=MockAgent,
        parameter_processors=[],
    )

    with pytest.raises(ValueError, match="Tool description must be a ToolDescription object."):
        await factory()


@pytest.mark.asyncio
async def test_pydantic_processor():
    factory = EntityFactory(
        MockEntityWithPydantic,
        parameter_processors=[pydantic_processor],
    )
    instance = await factory(
        pydantic_param={"name": "pydantic_name", "value": 99},
        primitive_param=100,
    )
    assert isinstance(instance, MockEntityWithPydantic)
    assert isinstance(instance.pydantic_param, MockPydanticModel)
    assert instance.pydantic_param.name == "pydantic_name"
    assert instance.pydantic_param.value == 99
    assert instance.primitive_param == 100


@pytest.mark.asyncio
async def test_combined_processor_usage():
    factory = EntityFactory(
        MockEntityWithDataclass,
        parameter_processors=[detect_and_convert_dataclasses, pydantic_processor],
    )

    instance = await factory(
        dataclass_param={"name": "dc_test", "value": 1},
        primitive_param="dc_value",
    )
    assert isinstance(instance, MockEntityWithDataclass)
    assert isinstance(instance.dataclass_param, MockDataclass)
    assert instance.dataclass_param.name == "dc_test"
    assert instance.primitive_param == "dc_value"


@pytest.mark.asyncio
async def test_trace_manager_processor():
    factory = EntityFactory(MockAgent, parameter_processors=[build_trace_manager_processor()])
    tool_description = ToolDescription(
        name="tool_name",
        description="A tool description",
        tool_properties={"param": {"type": "integer", "description": "A number"}},
        required_tool_properties=["param"],
    )

    instance = await factory(tool_description=tool_description)
    assert instance.trace_manager == get_trace_manager()
    assert instance.tool_description == tool_description


@pytest.mark.asyncio
async def test_agent_factory_invalid_tool_description():
    factory = AgentFactory(
        entity_class=MockAgent,
        parameter_processors=[],
    )

    invalid_tool_description = {
        "name": "mock_tool",
        "description": "A mock tool description",
        "tool_properties": {"key": {"type": "string", "description": "A test key"}},
        "required_tool_properties": ["key"],
    }

    with pytest.raises(ValueError, match="Tool description must be a ToolDescription object."):
        await factory(tool_description=invalid_tool_description)


@pytest.fixture(autouse=True)
def clear_project_context():
    set_current_project_id(None)
    yield
    set_current_project_id(None)


def _make_project(org_id: uuid.UUID) -> MagicMock:
    project = MagicMock()
    project.organization_id = org_id
    return project


@patch("ada_backend.services.entity_factory.get_db_session")
def test_project_reference_processor_fails_without_caller_context(mock_db_session):
    """build_project_reference_processor must raise if no caller project_id is set in context."""
    org_id = uuid.uuid4()
    referenced_project_id = str(uuid.uuid4())

    mock_session = MagicMock()
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)
    mock_db_session.return_value = mock_session
    mock_session.execute.return_value.scalar_one_or_none.return_value = _make_project(org_id)

    with patch("ada_backend.services.entity_factory.get_project", return_value=_make_project(org_id)):
        processor = build_project_reference_processor()
        with pytest.raises(ValueError, match="caller project context"):
            processor({"project_id": referenced_project_id}, {})


@patch("ada_backend.services.entity_factory.get_db_session")
def test_project_reference_processor_blocks_cross_org(mock_db_session):
    """build_project_reference_processor must raise when caller and referenced projects differ in org."""
    caller_org = uuid.uuid4()
    referenced_org = uuid.uuid4()
    caller_project_id = uuid.uuid4()
    referenced_project_id = str(uuid.uuid4())

    mock_session = MagicMock()
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)
    mock_db_session.return_value = mock_session

    def fake_get_project(_session, pid):
        if pid == caller_project_id:
            return _make_project(caller_org)
        return _make_project(referenced_org)

    with patch("ada_backend.services.entity_factory.get_project", side_effect=fake_get_project):
        set_current_project_id(caller_project_id)
        processor = build_project_reference_processor()
        with pytest.raises(ValueError, match="Cross-organization"):
            processor({"project_id": referenced_project_id}, {})


@patch("ada_backend.services.entity_factory.get_db_session")
def test_project_reference_processor_allows_same_org(mock_db_session):
    """build_project_reference_processor must pass when caller and referenced share the same org."""
    shared_org = uuid.uuid4()
    caller_project_id = uuid.uuid4()
    referenced_project_id = str(uuid.uuid4())
    gr_id = uuid.uuid4()

    mock_session = MagicMock()
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)
    mock_db_session.return_value = mock_session

    mock_gr = MagicMock()
    mock_gr.id = gr_id

    with (
        patch("ada_backend.services.entity_factory.get_project", return_value=_make_project(shared_org)),
        patch(
            "ada_backend.repositories.graph_runner_repository.get_graph_runner_for_env",
            return_value=mock_gr,
        ),
        patch(
            "ada_backend.services.agent_runner_service.get_agent_for_project",
            return_value=MagicMock(),
        ),
    ):
        set_current_project_id(caller_project_id)
        processor = build_project_reference_processor()
        params = {"project_id": referenced_project_id}
        result = processor(params, {})
        assert "graph_runner" in result


def test_get_llm_provider_and_model():
    correct_name = "openai:gpt-5"
    correct_name_with_colons = "custom-provider:bge-m3:567m"
    bad_name = "unknown-model"

    provider_correct, model_correct = get_llm_provider_and_model(correct_name)
    assert provider_correct == "openai"
    assert model_correct == "gpt-5"

    provider_with_colons, model_with_colons = get_llm_provider_and_model(correct_name_with_colons)
    assert provider_with_colons == "custom-provider"
    assert model_with_colons == "bge-m3:567m"

    with pytest.raises(ValueError, match="Invalid LLM model format: unknown-model. Expected 'provider:model_name'."):
        get_llm_provider_and_model(bad_name)
