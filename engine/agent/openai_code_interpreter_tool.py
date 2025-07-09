from typing import Optional

from openinference.semconv.trace import SpanAttributes
from opentelemetry.trace import get_current_span

from engine.agent.agent import Agent, AgentPayload, ChatMessage, ToolDescription
from engine.llm_services.llm_service import CodeInterpreterService
from engine.trace.trace_manager import TraceManager


DEFAULT_OPENAI_CODE_INTERPRETER_TOOL_DESCRIPTION = ToolDescription(
    name="OpenAI_Code_Interpreter",
    description="Execute Python code using OpenAI's code interpreter in a secure sandbox environment.",
    tool_properties={
        "code_prompt": {
            "type": "string",
            "description": "The Python code or task description to execute using the code interpreter.",
        },
    },
    required_tool_properties=["code_prompt"],
)


class OpenAICodeInterpreterTool(Agent):
    def __init__(
        self,
        code_interpreter_service: CodeInterpreterService,
        trace_manager: TraceManager,
        component_instance_name: str,
        tool_description: ToolDescription = DEFAULT_OPENAI_CODE_INTERPRETER_TOOL_DESCRIPTION,
    ):
        super().__init__(
            trace_manager=trace_manager,
            tool_description=tool_description,
            component_instance_name=component_instance_name,
        )
        self._code_interpreter_service = code_interpreter_service

    async def _run_without_trace(
        self,
        *inputs: AgentPayload,
        code_prompt: Optional[str] = None,
    ) -> AgentPayload:
        agent_input = inputs[0]

        # Ensure we have a valid string prompt
        if code_prompt:
            prompt_str = code_prompt
        elif agent_input.last_message and agent_input.last_message.content:
            prompt_str = str(agent_input.last_message.content)
        else:
            raise ValueError("No valid code prompt provided")

        span = get_current_span()
        span.set_attributes(
            {
                SpanAttributes.INPUT_VALUE: prompt_str,
                SpanAttributes.LLM_MODEL_NAME: self._code_interpreter_service._model_name,
            }
        )
        output = self._code_interpreter_service.execute_code(prompt_str)
        return AgentPayload(messages=[ChatMessage(role="assistant", content=output)])
