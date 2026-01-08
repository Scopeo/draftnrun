from ada_backend.database.seed.utils import COMPONENT_VERSION_UUIDS
from ada_backend.services.registry import FACTORY_REGISTRY
from engine.components.synthesizer import Synthesizer
from engine.components.tools.mcp.remote_mcp_tool import RemoteMCPTool
from engine.components.types import ComponentAttributes, ToolDescription
from engine.llm_services.llm_service import CompletionService
from engine.trace.trace_context import set_trace_manager
from tests.mocks.trace_manager import MockTraceManager


def test_synthesizer_registration():
    # Register a new entity class with the registry
    set_trace_manager(MockTraceManager(project_name="test_project"))
    factory = FACTORY_REGISTRY.get(component_version_id=COMPONENT_VERSION_UUIDS["synthesizer"])
    assert factory is not None

    # Create an instance of the registered entity
    synthesizer = factory(
        trace_manager=MockTraceManager(project_name="test_project"),
        completion_model="openai:gpt-4.1-mini",
        temperature=0.99,
    )
    assert synthesizer is not None
    assert isinstance(synthesizer, Synthesizer)
    assert synthesizer._completion_service is not None
    assert isinstance(synthesizer._completion_service, CompletionService)
    assert synthesizer._completion_service._model_name == "gpt-4.1-mini"
    assert synthesizer._completion_service._invocation_parameters.get("temperature") == 0.99


def test_remote_mcp_factory_calls_async_constructor(monkeypatch):
    set_trace_manager(MockTraceManager(project_name="test_project"))

    async def fake_from_mcp_server(cls, **kwargs):
        return {"constructed_with": kwargs}

    monkeypatch.setattr(RemoteMCPTool, "from_mcp_server", classmethod(fake_from_mcp_server))

    tool_desc = ToolDescription(
        name="placeholder",
        description="placeholder",
        tool_properties={},
        required_tool_properties=[],
    )

    result = FACTORY_REGISTRY.create(
        component_version_id=COMPONENT_VERSION_UUIDS["remote_mcp_tool"],
        component_attributes=ComponentAttributes(component_instance_name="remote"),
        server_url="https://mcp.example.com/sse",
        tool_description=tool_desc,
    )

    assert result["constructed_with"]["server_url"] == "https://mcp.example.com/sse"
    assert "tool_description" not in result["constructed_with"]
