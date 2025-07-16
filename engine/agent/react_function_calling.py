import logging
import json
import asyncio
from typing import Optional

from opentelemetry import trace as trace_api
from openinference.semconv.trace import OpenInferenceSpanKindValues, SpanAttributes
from openai.types.chat import ChatCompletionMessageToolCall
from e2b_code_interpreter import Sandbox as E2BSandbox

from engine.agent.agent import (
    Agent,
    AgentPayload,
    ToolDescription,
    ChatMessage,
)
from engine.graph_runner.runnable import Runnable
from engine.agent.history_message_handling import HistoryMessageHandler
from engine.trace.trace_manager import TraceManager
from engine.llm_services.llm_service import CompletionService
from engine.agent.utils_prompt import fill_prompt_template_with_dictionary
from settings import settings


LOGGER = logging.getLogger(__name__)

INITIAL_PROMPT = (
    "Don't make assumptions about what values to plug into functions. Ask for "
    "clarification if a user request is ambiguous. "
)
DEFAULT_FALLBACK_REACT_ANSWER = "I'm sorry, I couldn't find a solution to your problem."
CODE_RUNNER_TOOLS = ["python_code_interpreter", "terminal_command"]


class ReActAgent(Agent):
    def __init__(
        self,
        completion_service: CompletionService,
        trace_manager: TraceManager,
        tool_description: ToolDescription,
        component_instance_name: str,
        agent_tools: Optional[list[Runnable] | Runnable] = None,
        run_tools_in_parallel: bool = True,
        initial_prompt: str = INITIAL_PROMPT,
        fallback_react_answer: str = DEFAULT_FALLBACK_REACT_ANSWER,
        max_iterations: int = 3,
        max_tools_per_iteration: Optional[int] = 4,
        input_data_field_for_messages_history: str = "messages",
        first_history_messages: int = 1,
        last_history_messages: int = 50,
        allow_tool_shortcuts: bool = False,
    ) -> None:
        super().__init__(
            trace_manager=trace_manager,
            tool_description=tool_description,
            component_instance_name=component_instance_name,
        )
        self.run_tools_in_parallel = run_tools_in_parallel
        self.running_tool_way = "parallel" if self.run_tools_in_parallel else "series"
        if agent_tools is None:
            self.agent_tools = []
        else:
            self.agent_tools = agent_tools if isinstance(agent_tools, list) else [agent_tools]
        self.initial_prompt = initial_prompt
        self.fallback_react_answer = fallback_react_answer
        self._first_history_messages = first_history_messages
        self._last_history_messages = last_history_messages
        self._memory_handling = HistoryMessageHandler(self._first_history_messages, self._last_history_messages)
        self._max_iterations = max_iterations
        self._max_tools_per_iteration = max_tools_per_iteration
        self._current_iteration = 0
        self._completion_service = completion_service
        self.input_data_field_for_messages_history = input_data_field_for_messages_history
        self._allow_tool_shortcuts = allow_tool_shortcuts
        self._shared_sandbox: Optional[E2BSandbox] = None
        self._e2b_api_key = getattr(settings, "E2B_API_KEY", None)

    def _ensure_shared_sandbox(self) -> E2BSandbox:
        """Create and return a shared sandbox, validating API key first."""
        if not self._shared_sandbox:
            if not self._e2b_api_key:
                raise ValueError("E2B API key not configured")
            self._shared_sandbox = E2BSandbox(api_key=self._e2b_api_key)
        return self._shared_sandbox

    def _cleanup_shared_sandbox(self) -> None:
        """Safely clean up the shared sandbox."""
        if self._shared_sandbox:
            try:
                self._shared_sandbox.kill()
            except Exception as e:
                LOGGER.error(f"Failed to kill shared sandbox: {e}")
            finally:
                self._shared_sandbox = None

    async def _run_tool_call(
        self, *original_agent_inputs: AgentPayload, tool_call: ChatCompletionMessageToolCall
    ) -> tuple[str, AgentPayload]:
        tool_call_id = tool_call.id
        tool_function_name = tool_call.function.name
        tool_arguments = json.loads(tool_call.function.arguments)
        LOGGER.info(f"Tool call: {tool_function_name} with query string: {tool_arguments} and id: {tool_call_id}")

        tool_to_use: Runnable = next(
            tool for tool in self.agent_tools if tool.tool_description.name == tool_function_name
        )
        if tool_function_name in CODE_RUNNER_TOOLS:
            tool_arguments["shared_sandbox"] = self._ensure_shared_sandbox()
        tool_output = await tool_to_use.run(*original_agent_inputs, **tool_arguments)
        return tool_call_id, tool_output

    async def _process_tool_calls(
        self, *original_agent_inputs: AgentPayload, tool_calls: list[dict]
    ) -> tuple[dict[str, AgentPayload], list[dict]]:
        tool_outputs: dict[str, AgentPayload] = {}

        # Determine max tools to execute
        max_tools = len(tool_calls)
        if self._max_tools_per_iteration is not None:
            max_tools = min(max_tools, self._max_tools_per_iteration)

        if len(tool_calls) > max_tools:
            LOGGER.warning(f"Limiting tool calls from {len(tool_calls)} to {max_tools} per iteration")

        # Get the subset of tool calls we'll actually process
        tools_to_process = tool_calls[:max_tools]

        # Process the allowed number of tools
        try:
            if self.run_tools_in_parallel:
                tasks = [
                    self._run_tool_call(
                        *original_agent_inputs,
                        tool_call=tool_call,
                    )
                    for tool_call in tools_to_process
                ]
                results = await asyncio.gather(*tasks)
                for tool_id, agent_output in results:
                    tool_outputs[tool_id] = agent_output
            else:
                # Process sequentially
                for tool_call in tools_to_process:
                    tool_call_id, tool_output = await self._run_tool_call(
                        *original_agent_inputs,
                        tool_call=tool_call,
                    )
                    tool_outputs[tool_call_id] = tool_output
        except Exception as e:
            # Clean up sandbox on any exception during tool execution
            self._cleanup_shared_sandbox()
            raise e

        return tool_outputs, tools_to_process

    async def _run_without_trace(self, *inputs: AgentPayload | dict, **kwargs) -> AgentPayload:
        """Runs ReActAgent. Only one input is allowed."""
        try:
            original_agent_input = inputs[0]
            if not isinstance(original_agent_input, AgentPayload):
                # TODO : Will be suppressed when AgentPayload will be suppressed
                original_agent_input["messages"] = original_agent_input[self.input_data_field_for_messages_history]
                original_agent_input = AgentPayload(**original_agent_input)
            system_message = next((msg for msg in original_agent_input.messages if msg.role == "system"), None)
            if system_message is None:
                original_agent_input.messages.insert(
                    0,
                    ChatMessage(
                        role="system",
                        content=fill_prompt_template_with_dictionary(
                            original_agent_input.model_dump(),
                            self.initial_prompt,
                            self.component_instance_name,
                        ),
                    ),
                )
            else:
                # Some React derived agents are tools of React agents, hence we need
                # to replace the system message by the initial prompt
                original_agent_input.messages[0] = ChatMessage(
                    role="system",
                    content=self.initial_prompt,
                )
            agent_input = original_agent_input.model_copy(deep=True)
            history_messages_handled = self._memory_handling.get_truncated_messages_history(agent_input.messages)
            tool_choice = "auto" if self._current_iteration < self._max_iterations else "none"
            with self.trace_manager.start_span("Agentic reflexion") as span:
                llm_input_messages = [msg.model_dump() for msg in history_messages_handled]
                span.set_attributes(
                    {
                        SpanAttributes.OPENINFERENCE_SPAN_KIND: OpenInferenceSpanKindValues.LLM.value,
                        SpanAttributes.LLM_INPUT_MESSAGES: json.dumps(llm_input_messages),
                        SpanAttributes.LLM_MODEL_NAME: self._completion_service._model_name,
                    }
                )
                chat_response = self._completion_service.function_call(
                    messages=llm_input_messages,
                    tools=[agent.tool_description for agent in self.agent_tools],
                    tool_choice=tool_choice,
                )

                span.set_attributes(
                    {
                        SpanAttributes.LLM_OUTPUT_MESSAGES: json.dumps(chat_response.choices[0].message.model_dump()),
                    }
                )
                span.set_status(trace_api.StatusCode.OK)

                all_tool_calls = chat_response.choices[0].message.tool_calls

                if not all_tool_calls:
                    self.log_trace_event("No tool calls found in the response. Returning the chat response.")
                    imgs = get_images_from_message(history_messages_handled)
                    artifacts = {}
                    if imgs:
                        artifacts["images"] = imgs
                    else:
                        LOGGER.debug("No images found in the response.")
                    self._cleanup_shared_sandbox()
                    return AgentPayload(
                        messages=[ChatMessage(role="assistant", content=chat_response.choices[0].message.content)],
                        is_final=True,
                        artifacts=artifacts,
                    )

            # Process only the subset of tool calls that we want to execute
            agent_outputs, processed_tool_calls = await self._process_tool_calls(
                original_agent_input,
                tool_calls=all_tool_calls,
            )

            # Only add the tool calls we actually processed to the message history
            agent_input.messages.append(
                ChatMessage(
                    role="assistant",
                    content=None,
                    tool_calls=processed_tool_calls,
                )
            )
            # Add the tool outputs to the chat history
            agent_input.messages.extend(
                ChatMessage(
                    role="tool",
                    content=agent_output.last_message.content,
                    tool_call_id=tool_call_id,
                )
                for tool_call_id, agent_output in agent_outputs.items()
            )

            # If there's 0 or more than 1 final outputs, run the agent again
            successful_output_count = sum(agent_output.is_final for agent_output in agent_outputs.values())
            if successful_output_count == 1 and self._allow_tool_shortcuts:
                self.log_trace_event(
                    message=(
                        f"Found a unique successful output after {self._current_iteration + 1} "
                        f"iterations. Returning the final output."
                    )
                )
                final_output: AgentPayload = next(
                    agent_output for agent_output in agent_outputs.values() if agent_output.is_final
                )
                self._cleanup_shared_sandbox()
                return final_output

            elif self._current_iteration < self._max_iterations:
                self.log_trace_event(
                    message=(
                        f"Number of successful tool outputs: {successful_output_count}. " f"Running the agent again."
                    )
                )
                self._current_iteration += 1
                return await self._run_without_trace(agent_input)
            else:  # This should not happen if the "tool_choice" parameter works correctly on the LLM service
                self.log_trace_event(
                    message=(
                        f"Reached the maximum number of iterations ({self._max_iterations}). "
                        f"Returning the fallback answer: {self.fallback_react_answer}"
                    )
                )
                self._cleanup_shared_sandbox()
                return AgentPayload(
                    messages=[ChatMessage(role="assistant", content=self.fallback_react_answer)],
                    is_final=False,
                )
        except Exception as e:
            # Ensure sandbox cleanup on any unhandled exception
            self._cleanup_shared_sandbox()
            raise e


def get_dummy_ai_agent_description() -> ToolDescription:
    return ToolDescription(
        name="exemple_base_ai_agent",
        description="",
        tool_properties={},
        required_tool_properties=[],
    )


# TODO: handle other formats than png
def get_images_from_message(messages: list[ChatMessage]) -> list[str]:
    if messages:
        message = messages[-1]
        if message.content and "}" in message.content:
            json_end = message.content.rfind("}") + 1
            try:
                json_content = json.loads(message.content[:json_end])
                if "results" in json_content:
                    imgs = [result["png"] for result in json_content["results"] if "png" in result]
                else:
                    imgs = []
            except (
                json.JSONDecodeError,
                TypeError,
            ):
                LOGGER.debug("Parsing the image response from JSON failed")
                imgs = []
            return imgs
    return []
