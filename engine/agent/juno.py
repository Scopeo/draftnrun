import os
from pathlib import Path
from datetime import datetime

from engine.agent.agent import Agent, ToolDescription
from engine.agent.rag.rag import RAG
from engine.agent.rag import build_slack_rag_agent, build_notion_rag_agent, build_default_rag_agent
from engine.agent.react_function_calling import ReActAgent

from engine.agent.api_tools.tavily_search_tool import TavilyApiTool
from engine.trace.trace_manager import TraceManager
from engine.llm_services.llm_service import LLMService
from settings import load_yaml

BASE_DIR = Path(__file__).parents[2].resolve()
company_context = (
    load_yaml(BASE_DIR / "company_context.yaml") if os.path.exists(BASE_DIR / "company_context.yaml") else {}
)
ASSISTANT_NAME = company_context.get("assistant_name", "Juno")
COMPANY_NAME = company_context.get("company_name", "<company_name>")
COMPANY_DESCRIPTION = company_context.get("company_description", "")


class JunoAgent(ReActAgent):
    DATE_TEMPLATE = "We are on {date} and the time is {time}. \n"
    CONTEXT_TEMPLATE = (
        "You are a company chatbot assistant called {assistant_name} that has access to a "
        "wide variety of company data sources. You belong to the company {company_name} and "
        "all the people talking to you are employees of the company. You're goal is to help "
        "them as much as you can by providing them with the information they need.\n"
        "{company_description}"
    )
    INSTRUCTIONS_TEMPLATE = (
        "You only have two options for the answer: \n"
        "#### Answer with the tool's answer: \n"
        "- Copy the exact response string given by the tool. \n"
        "- Do not modify it and copy sources as well if they are provided. \n"
        "#### Answer that you cannot answer: \n"
        "- Write a response, in french, saying that you cannot answer "
        "the question and explaining what you have tried"
        "to get the answer. \n"
        "- If you think that you could get the answer "
        "with a bit more information from the user, you can ask for it. \n"
        "- Do not choose to answer that you cannot answer "
        "if you haven't used all the retrieval tools at your disposal. \n"
        "Only answer the question, and do it only with the information given by the tools.\n"
        "You cannot chose to answer that you don't know without using the tools before.\n"
        "- If you need to put a link in the answer, do it on markdown format: [text](link)\n"
    )

    PROMPT_TEMPLATE = DATE_TEMPLATE + CONTEXT_TEMPLATE + INSTRUCTIONS_TEMPLATE

    def __init__(
        self,
        llm_service: LLMService,
        trace_manager: TraceManager,
        tool_description: ToolDescription,
        component_instance_name: str,
        agent_tools: list[Agent],
        assistant_name: str,
        company_name: str,
        company_description: str,
        run_tools_in_parallel: bool = True,
    ) -> None:
        self.assistant_name = assistant_name
        self.company_name = company_name
        self.company_description = company_description
        super().__init__(
            llm_service=llm_service,
            trace_manager=trace_manager,
            component_instance_name=component_instance_name,
            agent_tools=agent_tools,
            tool_description=tool_description,
            run_tools_in_parallel=run_tools_in_parallel,
            initial_prompt=self._create_initial_prompt(),
        )

    def _create_initial_prompt(self) -> str:
        return self.PROMPT_TEMPLATE.format(
            date=datetime.now().strftime("%Y-%m-%d"),
            time=datetime.now().strftime("%H:%M:%S"),
            assistant_name=self.assistant_name,
            company_name=self.company_name,
            company_description=self.company_description,
        )

    @classmethod
    def from_defaults(
        cls,
        llm_service: LLMService,
        trace_manager: TraceManager,
        run_tools_in_parallel: bool = True,
        assistant_name: str = ASSISTANT_NAME,
        company_name: str = COMPANY_NAME,
        company_description: str = COMPANY_DESCRIPTION,
    ):
        rag_slack: RAG = build_slack_rag_agent(
            llm_service=llm_service,
            trace_manager=trace_manager,
            source_name="slack",
        )
        rag_notion: RAG = build_notion_rag_agent(
            llm_service=llm_service,
            trace_manager=trace_manager,
            source_name="notion",
        )
        rag_convention = build_default_rag_agent(
            llm_service=llm_service,
            trace_manager=trace_manager,
            source_name="scopeo_convention",
        )
        search_api_tool: Agent = TavilyApiTool(
            llm_service=llm_service,
            trace_manager=trace_manager,
        )
        tools = [
            search_api_tool,
            rag_slack,
            rag_convention,
            rag_notion,
        ]

        juno_description = ToolDescription(
            name="juno",
            description="A company chatbot assistant.",
            tool_properties={},
            required_tool_properties=[],
        )

        return cls(
            llm_service=llm_service,
            trace_manager=trace_manager,
            agent_tools=tools,
            component_instance_name="Juno Agent",
            tool_description=juno_description,
            run_tools_in_parallel=run_tools_in_parallel,
            assistant_name=assistant_name,
            company_name=company_name,
            company_description=company_description,
        )
