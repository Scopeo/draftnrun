import logging
import warnings
from typing import Optional

from pydantic import BaseModel

from engine.agent.agent import Agent, ToolDescription, AgentPayload
from engine.trace.trace_manager import TraceManager
from engine.llm_services.llm_service import LLMService
from engine.llm_services.openai_llm_service import OpenAILLMService

CATEGORY_SELECTION_PROMPT = (
    "You are a helpful assistant tasked with classifying user questions. "
    "Your task is to select the single most relevant category for the given question. \n"
    "Here are the list of categories: {categories}. \n"
    "The user's question is: {question}"
)
DEFAULT_SWITCH_TOOL_DESCRIPTION = ToolDescription(
    name="SwitchCategoricalPipeline",
    description="Switches between different agents based on a categorical input.",
    tool_properties={},
    required_tool_properties=[],
)

LOGGER = logging.getLogger(__name__)


class SelectedCategory(BaseModel):
    chosen_category: str


class SwitchCategoricalPipeline(Agent):
    """Agent that switches between different agents based on a categorical input."""

    def __init__(
        self,
        trace_manager: TraceManager,
        tool_description: ToolDescription,
        component_instance_name: str,
        categories: list[str],
        agents: list[Agent],
        llm_service: Optional[LLMService] = None,
        prompt_template: str = CATEGORY_SELECTION_PROMPT,
    ) -> None:
        warnings.warn(
            "SwitchCategoricalPipeline is deprecated and will be removed in a future version.",
            DeprecationWarning,
            stacklevel=2,
        )
        if len(categories) != len(agents):
            LOGGER.error("Number of categories and agents should be the same.")
        self.prompt_template = prompt_template
        self.llm_service = llm_service or OpenAILLMService(trace_manager)
        self.agent_router = {category: agent for category, agent in zip(categories, agents)}
        super().__init__(
            trace_manager,
            tool_description,
            component_instance_name,
        )

    async def select_category(self, agent_input: AgentPayload) -> SelectedCategory:
        response = await self.llm_service.async_constrained_complete(
            messages=[
                {
                    "role": "system",
                    "content": self.prompt_template.format(
                        categories=list(self.agent_router.keys()),
                        question=agent_input.last_message.content,
                    ),
                },
            ],
            response_format=SelectedCategory,
        )
        return response.chosen_category

    def select_agent(self, category: str) -> Agent:
        if category not in self.agent_router:
            LOGGER.error(f"Category {category} not found in the agent router.")
        return self.agent_router[category]

    async def _run_without_trace(self, *inputs: AgentPayload, **kwargs) -> AgentPayload:
        agent_input = inputs[0]
        category = await self.select_category(agent_input)
        agent = self.select_agent(category)
        return await agent.run(*inputs, **kwargs)
