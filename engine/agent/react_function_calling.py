import logging
import json
import asyncio
from datetime import datetime
from typing import Optional, Type, Any

from opentelemetry import trace as trace_api
from openinference.semconv.trace import OpenInferenceSpanKindValues, SpanAttributes
from openai.types.chat import ChatCompletionMessageToolCall
from e2b_code_interpreter import AsyncSandbox
from pydantic import BaseModel, Field

from engine.agent.agent import Agent
from engine.agent.types import (
    AgentPayload,
    ComponentAttributes,
    ToolDescription,
    ChatMessage,
)
from engine.graph_runner.runnable import Runnable
from engine.agent.history_message_handling import HistoryMessageHandler
from engine.agent.utils import load_str_to_json
from engine.trace.trace_manager import TraceManager
from engine.llm_services.llm_service import CompletionService
from engine.agent.utils_prompt import fill_prompt_template
from engine.agent.tools.python_code_runner import PYTHON_CODE_RUNNER_TOOL_DESCRIPTION
from engine.agent.tools.terminal_command_runner import TERMINAL_COMMAND_RUNNER_TOOL_DESCRIPTION
from engine.agent.tools.mcp_client_tool import MCPClientTool
from settings import settings

LOGGER = logging.getLogger(__name__)

INITIAL_PROMPT = (
    "Don't make assumptions about what values to plug into functions. Ask for "
    "clarification if a user request is ambiguous. "
)
DEFAULT_FALLBACK_REACT_ANSWER = "I couldn't find a solution to your problem."
CODE_RUNNER_TOOLS = [PYTHON_CODE_RUNNER_TOOL_DESCRIPTION.name, TERMINAL_COMMAND_RUNNER_TOOL_DESCRIPTION.name]

OUTPUT_TOOL_NAME = "chat_formatting_output_tool"
OUTPUT_TOOL_DESCRIPTION = (
    "Default tool to be used by the agent to answer in a structured format if no other tool is called"
)


class ReActAgentInputs(BaseModel):
    messages: list[ChatMessage] = Field(
        description="The history of messages in the conversation.",
    )
    initial_prompt: Optional[str] = Field(
        default=None,
        description="Initial prompt to use for the agent.",
        json_schema_extra={"disabled_as_input": True},
    )
    output_format: Optional[str | dict] = Field(
        default=None,
        description="Structured output format.",
        json_schema_extra={"disabled_as_input": True},
    )
    # Allow any other fields to be passed through
    model_config = {"extra": "allow"}


class ReActAgentOutputs(BaseModel):
    output: str = Field(description="The string content of the final message from the agent.")
    full_message: ChatMessage = Field(description="The full final message object from the agent.")
    is_final: bool = Field(default=False, description="Indicates if this is the final output of the agent.")
    artifacts: dict[str, Any] = Field(default_factory=dict, description="Artifacts produced by the agent.")


def format_output_tool_description(
    tool_name: str,
    tool_description: str,
    tool_properties: dict,
    required_properties: Optional[list] = None,
) -> ToolDescription:
    """
    Format an output tool description for the React agent.

    Args:
        tool_name: Name of the output tool
        tool_description: Description of what the tool does
        tool_properties: JSON schema defining the tool's parameters
        required_properties: List of required property names. If None, all properties are required.

    Returns:
        ToolDescription for the output tool
    """
    if required_properties is None:
        required_properties = list(tool_properties.keys())

    return ToolDescription(
        name=tool_name,
        description=tool_description,
        tool_properties=tool_properties,
        required_tool_properties=required_properties,
    )


def get_default_output_tool_description() -> ToolDescription:
    """
    Get the default output tool description for conversation answers.

    Returns:
        Default ToolDescription for structured conversation responses
    """
    return format_output_tool_description(
        tool_name="conversation_answer",
        tool_description=(
            "Generate a structured answer for the conversation. Use this tool when you have "
            "gathered enough information to provide a comprehensive response to the user's question. "
            "This tool allows you to provide both the answer content and indicate whether the "
            "conversation should continue or end."
        ),
        tool_properties={
            "answer": {
                "type": "string",
                "description": "The answer or response content for the user's question or request.",
            },
            "is_ending_conversation": {
                "type": "boolean",
                "description": "Whether this response should end the conversation (true) or "
                "allow for follow-up questions (false).",
            },
        },
        required_properties=["answer", "is_ending_conversation"],
    )


class ReActAgent(Agent):
    # TODO: It works as a migrated component, but it still uses legacy AgentPayload
    migrated = True

    @classmethod
    def get_canonical_ports(cls) -> dict[str, Optional[str]]:
        return {"input": "messages", "output": "output"}

    @classmethod
    def get_inputs_schema(cls) -> Type[BaseModel]:
        return ReActAgentInputs

    @classmethod
    def get_outputs_schema(cls) -> Type[BaseModel]:
        return ReActAgentOutputs

    def __init__(
        self,
        completion_service: CompletionService,
        trace_manager: TraceManager,
        tool_description: ToolDescription,
        component_attributes: ComponentAttributes,
        agent_tools: Optional[list[Runnable] | Runnable] = None,
        run_tools_in_parallel: bool = True,
        initial_prompt: str = INITIAL_PROMPT,
        max_iterations: int = 3,
        max_tools_per_iteration: Optional[int] = 4,
        input_data_field_for_messages_history: str = "messages",
        first_history_messages: int = 1,
        last_history_messages: int = 50,
        allow_tool_shortcuts: bool = False,
        date_in_system_prompt: bool = False,
        output_format: Optional[str | dict] = None,
    ) -> None:
        super().__init__(
            trace_manager=trace_manager,
            tool_description=tool_description,
            component_attributes=component_attributes,
        )
        self.run_tools_in_parallel = run_tools_in_parallel
        if agent_tools is None:
            self.agent_tools = []
        else:
            self.agent_tools = agent_tools if isinstance(agent_tools, list) else [agent_tools]
        self.initial_prompt = initial_prompt
        self._first_history_messages = first_history_messages
        self._last_history_messages = last_history_messages
        self._memory_handling = HistoryMessageHandler(self._first_history_messages, self._last_history_messages)
        self._max_iterations = max_iterations
        self._max_tools_per_iteration = max_tools_per_iteration
        self._current_iteration = 0
        self._completion_service = completion_service
        self.input_data_field_for_messages_history = input_data_field_for_messages_history
        self._allow_tool_shortcuts = allow_tool_shortcuts
        self._date_in_system_prompt = date_in_system_prompt
        self._shared_sandbox: Optional[AsyncSandbox] = None
        self._e2b_api_key = getattr(settings, "E2B_API_KEY", None)

        self._output_format = output_format
        self._output_tool_agent_description = self._get_output_tool_description(output_format)

    @staticmethod
    def _get_output_tool_description(output_format: str | dict | None) -> Optional[ToolDescription]:
        """
        Get the output tool description using the same pattern as RAG.

        Returns:
            ToolDescription if all required output tool parameters are set, None otherwise.
        """
        # If no output tool is configured, return None
        if not any([output_format]):
            return None

        # Parse JSON strings to appropriate data types
        if isinstance(output_format, str):
            parsed_output_tool_properies = load_str_to_json(output_format)
        else:
            parsed_output_tool_properies = output_format
        if parsed_output_tool_properies is None:
            return None

        required_properties = list[Any](parsed_output_tool_properies.keys())
        return ToolDescription(
            name=OUTPUT_TOOL_NAME,
            description=OUTPUT_TOOL_DESCRIPTION,
            tool_properties=parsed_output_tool_properies,
            required_tool_properties=required_properties,
        )

    # TODO: investigate if we can decouple the sandbox from the agent
    async def _ensure_shared_sandbox(self) -> AsyncSandbox:
        """Create and return a shared sandbox, validating API key first."""
        if not self._shared_sandbox:
            if not self._e2b_api_key:
                raise ValueError("E2B API key not configured")
            self._shared_sandbox = await AsyncSandbox.create(api_key=self._e2b_api_key)
        return self._shared_sandbox

    async def _cleanup_shared_sandbox(self) -> None:
        """Safely clean up the shared sandbox."""
        if self._shared_sandbox:
            try:
                await self._shared_sandbox.kill()
            except Exception as e:
                LOGGER.error(f"Failed to kill shared sandbox: {e}")
            finally:
                self._shared_sandbox = None

    async def _ensure_mcp_tools_initialized(self) -> None:
        """Initialize all MCP tools if they haven't been initialized yet."""
        for tool in self.agent_tools:
            if isinstance(tool, MCPClientTool) and tool.session is None:
                try:
                    await tool.initialize()
                except Exception as e:
                    LOGGER.error(f"Failed to initialize MCP tool {tool.tool_description.name}: {e}")

    async def _cleanup_mcp_tools(self) -> None:
        """Safely clean up MCP tools."""
        for tool in self.agent_tools:
            if isinstance(tool, MCPClientTool) and tool.session:
                try:
                    await tool.close()
                except Exception as e:
                    LOGGER.error(f"Failed to close MCP tool {tool.tool_description.name}: {e}")

    async def _cleanup_resources(self) -> None:
        """Clean up all resources including sandbox and MCP tools."""
        await self._cleanup_shared_sandbox()
        await self._cleanup_mcp_tools()

    # --- ORIGINAL CORE LOGIC (unchanged) ---
    async def _run_tool_call(
        self,
        *original_agent_inputs: AgentPayload,
        tool_call: ChatCompletionMessageToolCall,
        ctx: Optional[dict] = None,
    ) -> tuple[str, AgentPayload]:
        tool_call_id = tool_call.id
        tool_function_name = tool_call.function.name
        tool_arguments = json.loads(tool_call.function.arguments)
        LOGGER.info(f"Tool call: {tool_function_name} with query string: {tool_arguments} and id: {tool_call_id}")

        tool_to_use: Runnable = next(
            tool for tool in self.agent_tools if tool.tool_description.name == tool_function_name
        )
        if tool_function_name in CODE_RUNNER_TOOLS:
            tool_arguments["shared_sandbox"] = await self._ensure_shared_sandbox()
        try:
            LOGGER.info(f"Calling tool {tool_function_name} with arguments: {tool_arguments}")
            tool_output = await tool_to_use.run(*original_agent_inputs, ctx=ctx, **tool_arguments)
            LOGGER.info(f"Tool {tool_function_name} returned: {tool_output}")
        except Exception as e:
            LOGGER.error(f"Error running tool {tool_function_name}: {e}")
            tool_output = AgentPayload(messages=[ChatMessage(role="assistant", content=str(e))], error=str(e))
        return tool_call_id, tool_output

    async def _process_tool_calls(
        self, *original_agent_inputs: AgentPayload, tool_calls: list[dict], ctx: Optional[dict] = None
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

        if self.run_tools_in_parallel:
            tasks = [
                self._run_tool_call(
                    *original_agent_inputs,
                    tool_call=tool_call,
                    ctx=ctx,
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
                    ctx=ctx,
                )
                tool_outputs[tool_call_id] = tool_output
        return tool_outputs, tools_to_process

    async def _run_core(
        self,
        *inputs: AgentPayload | dict,
        ctx: Optional[dict] = None,
        initial_prompt: str,
        output_tool_description: ToolDescription | None,
        inputs_dict: Optional[dict] = None,
        **kwargs,
    ) -> AgentPayload:
        # Exact previous logic
        original_agent_input = inputs[0]
        if not isinstance(original_agent_input, AgentPayload):
            # Accept BaseModel-like inputs (e.g., NodeData) defensively
            if hasattr(original_agent_input, "model_dump") and callable(original_agent_input.model_dump):
                original_agent_input = original_agent_input.model_dump(exclude_none=True)
            # Ensure messages field populated from configured input key
            original_agent_input["messages"] = original_agent_input[self.input_data_field_for_messages_history]
            original_agent_input = AgentPayload(**original_agent_input)
        system_message = next((msg for msg in original_agent_input.messages if msg.role == "system"), None)

        # Prepare system prompt content
        system_prompt_content = initial_prompt
        if self._date_in_system_prompt:
            # TODO: add the timezone of the user
            current_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            system_prompt_content = f"Current date and time: {current_date}\n\n{initial_prompt}"

        inputs_dict = inputs_dict or {}
        if kwargs:
            inputs_dict = {**inputs_dict, **kwargs}

        merged_dict = {**(ctx or {}), **inputs_dict}

        filled_system_prompt = fill_prompt_template(
            prompt_template=system_prompt_content,
            component_name=self.component_attributes.component_instance_name,
            variables=merged_dict,
        )

        if system_message is None:
            original_agent_input.messages.insert(
                0,
                ChatMessage(
                    role="system",
                    content=filled_system_prompt,
                ),
            )
        else:
            # Some React derived agents are tools of React agents, hence we need
            # to replace the system message by the initial prompt
            original_agent_input.messages[0] = ChatMessage(
                role="system",
                content=filled_system_prompt,
            )
        agent_input = original_agent_input.model_copy(deep=True)
        history_messages_handled = self._memory_handling.get_truncated_messages_history(agent_input.messages)
        tool_choice = "auto" if self._current_iteration < self._max_iterations else "none"
        
        await self._ensure_mcp_tools_initialized()
        
        with self.trace_manager.start_span("Agentic reflexion") as span:
            llm_input_messages = [msg.model_dump() for msg in history_messages_handled]
            span.set_attributes(
                {
                    SpanAttributes.OPENINFERENCE_SPAN_KIND: OpenInferenceSpanKindValues.LLM.value,
                    SpanAttributes.LLM_INPUT_MESSAGES: json.dumps(llm_input_messages),
                    SpanAttributes.LLM_MODEL_NAME: self._completion_service._model_name,
                    "model_id": (
                        str(self._completion_service._model_id)
                        if self._completion_service._model_id is not None
                        else None
                    ),
                }
            )
            chat_response = await self._completion_service.function_call_async(
                messages=llm_input_messages,
                tools=[agent.tool_description for agent in self.agent_tools],
                tool_choice=tool_choice,
                structured_output_tool=output_tool_description,
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
                await self._cleanup_resources()
                return AgentPayload(
                    messages=[ChatMessage(role="assistant", content=chat_response.choices[0].message.content)],
                    is_final=True,
                    artifacts=artifacts,
                )

        agent_outputs, processed_tool_calls = await self._process_tool_calls(
            original_agent_input,
            tool_calls=all_tool_calls,
            ctx=ctx,
        )

        agent_input.messages.append(
            ChatMessage(
                role="assistant",
                content=None,
                tool_calls=processed_tool_calls,
            )
        )
        for tool_call_id, agent_output in agent_outputs.items():
            agent_input.messages.append(
                ChatMessage(
                    role="tool",
                    content=agent_output.messages[0].content if agent_output.messages else None,
                    tool_call_id=tool_call_id,
                )
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
            await self._cleanup_resources()
            return final_output

        elif self._current_iteration < self._max_iterations:
            self.log_trace_event(
                message=(f"Number of successful tool outputs: {successful_output_count}. " f"Running the agent again.")
            )
            self._current_iteration += 1
            return await self._run_core(
                agent_input,
                ctx=ctx,
                initial_prompt=initial_prompt,
                output_tool_description=output_tool_description,
                inputs_dict=inputs_dict,
                **kwargs,
            )
        else:
            LOGGER.error(
                f"Reached the maximum number of iterations ({self._max_iterations}) and still asks for tools."
                " This should not happen."
            )

            await self._cleanup_resources()
            return AgentPayload(
                messages=[ChatMessage(role="assistant", content=DEFAULT_FALLBACK_REACT_ANSWER)],
                is_final=False,
            )

    # --- Thin adapter to typed I/O ---
    async def _run_without_io_trace(self, inputs: ReActAgentInputs, ctx: dict) -> ReActAgentOutputs:
        # Map typed inputs to the original call style
        initial_prompt = inputs.initial_prompt or self.initial_prompt
        output_format = inputs.output_format or self._output_format
        output_tool_description = self._get_output_tool_description(output_format)

        payload_dict = inputs.model_dump(exclude_none=True)
        agent_payload = AgentPayload(**payload_dict) if "messages" in payload_dict else payload_dict

        # Extract inputs_dict from original ReActAgentInputs for template variable filling
        # Exclude messages and AgentPayload-specific fields (error, artifacts, is_final)
        inputs_dict_for_template = {
            k: v for k, v in payload_dict.items() if k not in ["messages", "error", "artifacts", "is_final"]
        }

        core_result = await self._run_core(
            agent_payload,
            ctx=ctx,
            initial_prompt=initial_prompt,
            output_tool_description=output_tool_description,
            inputs_dict=inputs_dict_for_template,
        )

        # Map original output back to typed outputs
        final_message = (
            core_result.messages[-1] if core_result.messages else ChatMessage(role="assistant", content=None)
        )
        return ReActAgentOutputs(
            output=final_message.content or "",
            full_message=final_message,
            is_final=core_result.is_final,
            artifacts=core_result.artifacts or {},
        )


def get_dummy_ai_agent_description() -> ToolDescription:
    return ToolDescription(
        name="exemple_base_ai_agent",
        description="",
        tool_properties={},
        required_tool_properties=[],
    )


def get_images_from_message(messages: list[ChatMessage]) -> list[str]:
    if messages:
        message = messages[-1]
        if message.content and "}" in message.content:
            try:
                json_content = json.loads(message.content)
                if "artifacts" in json_content and "images" in json_content["artifacts"]:
                    imgs = json_content["artifacts"]["images"]
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
