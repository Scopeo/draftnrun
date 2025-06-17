from unittest.mock import MagicMock, patch

import pytest

from engine.agent.juno import JunoAgent
from engine.agent.agent import ToolDescription
from engine.agent.rag.rag import RAG
from engine.agent.api_tools.tavily_search_tool import TavilyApiTool
from engine.trace.trace_manager import TraceManager
from engine.llm_services.llm_service import LLMService


@pytest.fixture
def setup_agent():
    llm_service = MagicMock(spec=LLMService)
    trace_manager = MagicMock(spec=TraceManager)
    tool_description = ToolDescription(
        name="juno",
        description="A company chatbot assistant.",
        tool_properties={},
        required_tool_properties=[],
    )
    tools = [
        MagicMock(spec=TavilyApiTool),
        MagicMock(spec=RAG),
        MagicMock(spec=RAG),
    ]
    assistant_name = "TestAssistant"
    company_name = "TestCompany"
    company_description = "TestDescription"
    component_instance_name = "Test Component"
    return (
        llm_service,
        trace_manager,
        tool_description,
        tools,
        assistant_name,
        company_name,
        company_description,
        component_instance_name,
    )


def test_agent_initialization(setup_agent):
    (
        llm_service,
        trace_manager,
        tool_description,
        tools,
        assistant_name,
        company_name,
        company_description,
        component_instance_name,
    ) = setup_agent
    agent = JunoAgent(
        llm_service=llm_service,
        trace_manager=trace_manager,
        tool_description=tool_description,
        component_instance_name=component_instance_name,
        agent_tools=tools,
        assistant_name=assistant_name,
        company_name=company_name,
        company_description=company_description,
    )
    assert agent.assistant_name == assistant_name
    assert agent.company_name == company_name
    assert agent.company_description == company_description
    assert agent.trace_manager == trace_manager
    assert agent.agent_tools == tools
    assert agent.tool_description == tool_description
    assert agent.component_instance_name == component_instance_name


def test_from_default(setup_agent):
    llm_service, trace_manager, _, _, assistant_name, company_name, company_description, _ = setup_agent
    with patch("engine.agent.juno.TavilyApiTool") as mock_tavily_api_tool:
        mock_tavily_api_tool_instance = MagicMock(spec=TavilyApiTool)
        mock_tavily_api_tool.return_value = mock_tavily_api_tool_instance
        agent = JunoAgent.from_defaults(
            llm_service=llm_service,
            trace_manager=trace_manager,
            assistant_name=assistant_name,
            company_name=company_name,
            company_description=company_description,
        )
        assert agent.assistant_name == assistant_name
        assert agent.company_name == company_name
        assert agent.company_description == company_description
        assert isinstance(agent.agent_tools[1], RAG)
        assert isinstance(agent.agent_tools[2], RAG)
        assert agent.tool_description.name == "juno"
        assert agent.tool_description.description == "A company chatbot assistant."
