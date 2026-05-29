"""Regression tests for agent/component building behavior."""

from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from ada_backend.database.seed.constants import COMPLETION_MODEL_IN_DB, TEMPERATURE_IN_DB
from ada_backend.database.seed.utils import COMPONENT_VERSION_UUIDS
from ada_backend.services import agent_builder_service, entity_factory
from engine.components.ai_agent import AIAgent
from engine.components.types import ComponentAttributes, ToolDescription


def _make_tool_description(name: str = "test_tool") -> ToolDescription:
    return ToolDescription(name=name, description="", tool_properties={}, required_tool_properties=[])


def _make_ai_agent(agent_tools: list, skip_tools_with_missing_oauth: bool = True) -> AIAgent:
    completion_service = MagicMock()
    trace_manager = MagicMock()
    trace_manager.start_span.return_value.__enter__ = MagicMock(return_value=MagicMock())
    trace_manager.start_span.return_value.__exit__ = MagicMock(return_value=False)
    return AIAgent(
        completion_service=completion_service,
        trace_manager=trace_manager,
        tool_description=_make_tool_description("agent"),
        component_attributes=ComponentAttributes(
            component_instance_name="test_agent",
            component_instance_id=None,
        ),
        agent_tools=agent_tools,
        skip_tools_with_missing_oauth=skip_tools_with_missing_oauth,
    )


def _make_tool(name: str, available: bool) -> MagicMock:
    tool = MagicMock()
    tool.is_available.return_value = available
    tool.get_tool_descriptions.return_value = [_make_tool_description(name)]
    tool.component_attributes.component_instance_name = name
    return tool


def test_unavailable_tool_skipped_when_flag_enabled():
    available = _make_tool("slack", available=True)
    unavailable = _make_tool("gmail", available=False)

    agent = _make_ai_agent([available, unavailable], skip_tools_with_missing_oauth=True)

    assert "slack" in agent._tool_registry
    assert "gmail" not in agent._tool_registry


def test_unavailable_tool_included_when_flag_disabled():
    available = _make_tool("slack", available=True)
    unavailable = _make_tool("gmail", available=False)

    agent = _make_ai_agent([available, unavailable], skip_tools_with_missing_oauth=False)

    assert "slack" in agent._tool_registry
    assert "gmail" in agent._tool_registry


def test_available_tool_always_included():
    tool = _make_tool("hubspot", available=True)

    agent = _make_ai_agent([tool], skip_tools_with_missing_oauth=True)

    assert "hubspot" in agent._tool_registry


def test_is_available_not_called_when_flag_disabled():
    tool = _make_tool("slack", available=False)

    _make_ai_agent([tool], skip_tools_with_missing_oauth=False)

    tool.is_available.assert_not_called()


def test_no_tools_skipped_when_all_available():
    tools = [_make_tool(name, available=True) for name in ("slack", "gmail", "outlook")]

    agent = _make_ai_agent(tools, skip_tools_with_missing_oauth=True)

    assert set(agent._tool_registry.keys()) == {"slack", "gmail", "outlook"}


@pytest.mark.asyncio
async def test_llm_component_instantiation_reuses_builder_session_for_model_id(monkeypatch):
    component_instance_id = uuid4()
    model_id = uuid4()
    session = MagicMock(name="builder_session")

    class FakeCompletionService:
        def __init__(
            self,
            provider,
            model_name,
            trace_manager,
            temperature,
            api_key,
            verbosity,
            reasoning,
            model_id,
        ):
            self.provider = provider
            self.model_name = model_name
            self.trace_manager = trace_manager
            self.temperature = temperature
            self.api_key = api_key
            self.verbosity = verbosity
            self.reasoning = reasoning
            self._model_id = model_id

    component_instance = SimpleNamespace(
        id=component_instance_id,
        component_version_id=COMPONENT_VERSION_UUIDS["llm_call"],
        name="AI",
        ref="ai",
    )

    monkeypatch.setattr(
        agent_builder_service,
        "get_component_instance_by_id",
        lambda received_session, received_id: component_instance,
    )
    monkeypatch.setattr(agent_builder_service, "get_component_name_from_instance", lambda *_: "AI")
    monkeypatch.setattr(
        agent_builder_service,
        "get_component_params",
        lambda *_args, **_kwargs: {
            COMPLETION_MODEL_IN_DB: "openai:gpt-4.1",
            TEMPERATURE_IN_DB: 0.2,
            "api_key": "test-key",
            "verbosity": "low",
            "reasoning": "minimal",
        },
    )
    monkeypatch.setattr(agent_builder_service, "get_integration_from_component", lambda *_: None)
    monkeypatch.setattr(agent_builder_service, "get_component_sub_components", lambda *_: [])
    monkeypatch.setattr(agent_builder_service, "get_global_parameters_by_component_version_id", lambda *_: [])
    monkeypatch.setattr(agent_builder_service, "replace_secret_placeholders", lambda params, _secrets: params)
    monkeypatch.setattr(agent_builder_service, "generate_tool_description", lambda *_: _make_tool_description("ai"))
    monkeypatch.setattr(agent_builder_service, "get_base_component_from_version", lambda *_: None)

    def fake_get_model_id_by_name_service(received_session, model_name):
        assert received_session is session
        assert model_name == "gpt-4.1"
        return model_id

    monkeypatch.setattr(agent_builder_service, "get_model_id_by_name_service", fake_get_model_id_by_name_service)
    monkeypatch.setattr(entity_factory, "CompletionService", FakeCompletionService)
    monkeypatch.setattr(entity_factory, "get_trace_manager", lambda: MagicMock())
    monkeypatch.setattr(entity_factory, "get_db_session", MagicMock(side_effect=AssertionError("nested DB session")))

    component = await agent_builder_service.instantiate_component(session, component_instance_id)

    completion_service = component._completion_service
    assert completion_service.provider == "openai"
    assert completion_service.model_name == "gpt-4.1"
    assert completion_service.temperature == 0.2
    assert completion_service.api_key == "test-key"
    assert completion_service.verbosity == "low"
    assert completion_service.reasoning == "minimal"
    assert completion_service._model_id == model_id
