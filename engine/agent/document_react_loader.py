import logging

from engine.agent.document_enhanced_llm_call import DocumentEnhancedLLMCallAgent
from engine.agent.react_function_calling import ReActAgent
from engine.agent.types import (
    ComponentAttributes,
    ToolDescription,
)
from engine.agent.utils_prompt import fill_prompt_template
from engine.llm_services.llm_service import LLMService
from engine.trace.trace_manager import TraceManager

LOGGER = logging.getLogger(__name__)

INITIAL_PROMPT = (
    "You are an assistant specialized in assisting users with questions regarding documentation."
    "You are provided a description of a folder of documents that you can access via a document loader enhanced"
    " LLM call agent. Given a query from a user, you are task to call the tool that are you are provided"
    " that loads the documents that are relevant to the query. When calling the tool, keep the query as it is."
    "Focus on choosing according to the query the most relevant documents to load regarding the description of the"
    "documents that you can access."
    "- If there is not a clear set of documents to load, you can ask the user to confirm if the best candidates"
    "that you identify are the one the user is interested to load."
    "-If the choices of documents is clear, always call for the tool.\n\n"
    "Here is a description in an ascii tree of the documents available: \n\n"
    "{{documents_tree}}\n\n"
)


def get_document_react_loader_tool_description() -> ToolDescription:
    return ToolDescription(
        name="document_react_loader_agent",
        description="A agent able to load documents and load them in a context window. "
        "The agent takes a query."
        "The query must be fully detailed and include all essential words, "
        "including interrogative adverbs, as well as information of the documents to load.",
        tool_properties={
            "query_text": {
                "type": "string",
                "description": "A full-length, well-formed search query "
                "preserving all key elements from the user's input.",
            },
        },
        required_tool_properties=[],
    )


class DocumentReactLoaderAgent(ReActAgent):
    def __init__(
        self,
        llm_service: LLMService,
        trace_manager: TraceManager,
        component_attributes: ComponentAttributes,
        document_enhanced_llm_call_agent: DocumentEnhancedLLMCallAgent,
        prompt: str = INITIAL_PROMPT,
        tool_description: ToolDescription = get_document_react_loader_tool_description(),
    ) -> None:
        self.agent_tools = [document_enhanced_llm_call_agent]
        initial_prompt = self.get_initial_prompt(prompt, document_enhanced_llm_call_agent)
        super().__init__(
            llm_service=llm_service,
            trace_manager=trace_manager,
            component_attributes=component_attributes,
            tool_description=tool_description,
            initial_prompt=initial_prompt,
            agent_tools=[document_enhanced_llm_call_agent],
        )

    def get_initial_prompt(self, initial_prompt, document_enhanced_llm_call_agent) -> str:
        return fill_prompt_template(
            initial_prompt,
            component_name="DocumentReactLoaderAgent",
            variables={"documents_tree": document_enhanced_llm_call_agent.tree_of_documents},
        )
