import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Optional, Type

from openai.types.chat import ChatCompletionMessageToolCall
from openinference.semconv.trace import OpenInferenceSpanKindValues, SpanAttributes
from opentelemetry import trace as trace_api
from pydantic import BaseModel, Field

from ada_backend.database.models import UIComponent, UIComponentProperties
from engine.components.component import Component
from engine.components.history_message_handling import HistoryMessageHandler
from engine.components.rag.formatter import Formatter
from engine.components.rag.retriever import RETRIEVER_CITATION_INSTRUCTION, RETRIEVER_TOOL_DESCRIPTION
from engine.components.types import AgentPayload, ChatMessage, ComponentAttributes, SourcedResponse, ToolDescription
from engine.components.utils import extract_source_ranks, load_str_to_json, merge_constrained_output_to_root
from engine.components.utils_prompt import fill_prompt_template
from engine.graph_runner.runnable import Runnable
from engine.llm_services.llm_service import CompletionService
from engine.trace.trace_manager import TraceManager

LOGGER = logging.getLogger(__name__)

INITIAL_PROMPT = (
    "Don't make assumptions about what values to plug into functions. Ask for "
    "clarification if a user request is ambiguous. "
)

DEFAULT_FALLBACK_REACT_ANSWER = "I couldn't find a solution to your problem."

OUTPUT_TOOL_NAME = "chat_formatting_output_tool"
OUTPUT_TOOL_DESCRIPTION = (
    "Default tool to be used by the agent to answer in a structured format if no other tool is called"
)
SYSTEM_PROMPT_DEFAULT = (
    "Act as a helpful assistant. "
    "You can use tools to answer questions,"
    " but you can also answer directly if you have enough information."
)


class AIAgentInputs(BaseModel):
    messages: list[ChatMessage] = Field(
        description="The history of messages in the conversation.",
    )
    initial_prompt: Optional[str] = Field(
        default=SYSTEM_PROMPT_DEFAULT,
        description=(
            "This prompt will be used to initialize the agent and set its behavior."
            " It can be used to provide context or instructions for the agent."
            " It will be used as the first message of the conversation in the agent's memory."
            " You can use it to set the agent's personality, role,"
            "or to provide specific instructions on how to handle certain types of questions."
            " The conversation you have with the agent (or your single message)"
            " is going to be added after this first message."
        ),
        json_schema_extra={
            "is_tool_input": False,
            "ui_component": UIComponent.TEXTAREA,
            "ui_component_properties": UIComponentProperties(
                label="System Prompt",
            ).model_dump(exclude_unset=True, exclude_none=True),
        },
    )
    output_format: Optional[str | dict] = Field(
        default=None,
        description=(
            "JSON schema defining the properties/parameters of the output tool. "
            'Example: {"answer": {"type": "string", "description": "The answer content"}, '
            '"is_ending_conversation": {"type": "boolean", "description": "End conversation?"}}'
        ),
        json_schema_extra={
            "is_tool_input": False,
            "ui_component": UIComponent.TEXTAREA,
            "ui_component_properties": UIComponentProperties(
                label="Output Format",
            ).model_dump(exclude_unset=True, exclude_none=True),
            "is_advanced": True,
        },
    )
    # Allow any other fields to be passed through
    model_config = {"extra": "allow"}


class AIAgentOutputs(BaseModel):
    output: str = Field(description="The string content of the final message from the agent.")
    full_message: ChatMessage = Field(description="The full final message object from the agent.")
    is_final: bool = Field(default=False, description="Indicates if this is the final output of the agent.")
    artifacts: dict[str, Any] = Field(default_factory=dict, description="Artifacts produced by the agent.")

    model_config = {"extra": "allow"}


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
                "description": (
                    "Whether this response should end the conversation (true) or "
                    "allow for follow-up questions (false)."
                ),
            },
        },
        required_properties=["answer", "is_ending_conversation"],
    )


class AIAgent(Component):
    # TODO: It works as a migrated component, but it still uses legacy AgentPayload
    migrated = True

    @classmethod
    def get_canonical_ports(cls) -> dict[str, Optional[str]]:
        return {"input": "messages", "output": "output"}

    @classmethod
    def get_inputs_schema(cls) -> Type[BaseModel]:
        return AIAgentInputs

    @classmethod
    def get_outputs_schema(cls) -> Type[BaseModel]:
        return AIAgentOutputs

    def __init__(
        self,
        completion_service: CompletionService,
        trace_manager: TraceManager,
        tool_description: ToolDescription,
        component_attributes: ComponentAttributes,
        agent_tools: Optional[list[Runnable] | Runnable] = None,
        run_tools_in_parallel: bool = True,
        max_iterations: int = 3,
        max_tools_per_iteration: Optional[int] = 4,
        input_data_field_for_messages_history: str = "messages",
        first_history_messages: int = 1,
        last_history_messages: int = 50,
        allow_tool_shortcuts: bool = False,
        date_in_system_prompt: bool = False,
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
        self._tool_registry: dict[str, tuple[Runnable, ToolDescription]] = {}

        # Tool cache is snapshotted at init; provide agent_tools up front.
        self._build_tool_cache()
        self._formatter = Formatter(add_sources=False, component_attributes=component_attributes)
        self._has_retriever_tool = self._check_for_retriever_tool()

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
            try:
                parsed_output_tool_properies = load_str_to_json(output_format)
            except ValueError as e:
                raise ValueError(f"Invalid 'output_format' parameter: {e}") from e
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

    def _build_tool_cache(self) -> None:
        """
        Expand tool descriptions for all agent tools.

        Calls get_tool_descriptions() on each tool to support:
        - Single-tool components (default): returns [self.tool_description]
        - Multi-tool components (e.g., RemoteMCPTool): returns multiple ToolDescriptions

        Caches a single mapping for both LLM listing and fast lookup.
        """
        self._tool_registry: dict[str, tuple[Runnable, ToolDescription]] = {}

        for tool in self.agent_tools:
            descriptions = tool.get_tool_descriptions()
            # Normalize to list if single ToolDescription
            if not isinstance(descriptions, list):
                descriptions = [descriptions]

            for desc in descriptions:
                if desc.name in self._tool_registry:
                    LOGGER.warning(f"Duplicate tool name '{desc.name}' - overriding previous mapping")
                self._tool_registry[desc.name] = (tool, desc)

    def _check_for_retriever_tool(self) -> bool:
        return RETRIEVER_TOOL_DESCRIPTION.name in self._tool_registry

    def _get_tool_descriptions_for_llm(self) -> list[ToolDescription]:
        """Return tool descriptions for LLM function calling."""
        return [desc for _, desc in self._tool_registry.values()]

    @staticmethod
    def _extract_file_metadata(ctx: Optional[dict]) -> list[dict[str, str]]:
        if not ctx:
            return []

        files_info = []
        for key, value in ctx.items():
            if isinstance(value, dict) and value.get("type") == "file":
                filename = value.get("filename", "")
                if filename:
                    files_info.append({
                        "key": key,
                        "filename": filename,
                    })
        return files_info

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

        tool_entry = self._tool_registry.get(tool_function_name)
        if tool_entry is None:
            raise ValueError(f"Tool {tool_function_name} not found in agent_tools.")
        tool_to_use, _ = tool_entry
        # TODO: replace this flag-based wiring with a proper function-calling→input translation hook
        if getattr(tool_to_use, "requires_tool_name", False):
            tool_arguments["tool_name"] = tool_function_name
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

        # TODO: Refactor logic. AI Agent is coupled to Retriever tool here. Tools should inject their own instructions
        # without AI Agent knowing the specifics
        if self._has_retriever_tool:
            system_prompt_content = f"{initial_prompt}\n{RETRIEVER_CITATION_INSTRUCTION}"

        if self._date_in_system_prompt:
            # TODO: add the timezone of the user
            current_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            system_prompt_content = f"Current date and time: {current_date}\n\n{system_prompt_content}"

        files_metadata = self._extract_file_metadata(ctx)
        if files_metadata:
            file_list = "\n".join([f"- {f['filename']}" for f in files_metadata])
            files_instruction = (
                "\n\nAvailable input files:\n"
                f"{file_list}\n\n"
                "You can reference these files directly by filename in your Python code "
                "(using the input_filepaths parameter)."
            )
            system_prompt_content += files_instruction

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
        tool_choice = "auto" if self._current_iteration + 1 < self._max_iterations else "none"
        with self.trace_manager.start_span("Agentic reflexion") as span:
            llm_input_messages = [msg.model_dump() for msg in history_messages_handled]
            span.set_attributes({
                SpanAttributes.OPENINFERENCE_SPAN_KIND: OpenInferenceSpanKindValues.LLM.value,
                SpanAttributes.LLM_INPUT_MESSAGES: json.dumps(llm_input_messages),
                SpanAttributes.LLM_MODEL_NAME: self._completion_service._model_name,
                "model_id": (
                    str(self._completion_service._model_id) if self._completion_service._model_id is not None else None
                ),
            })
            chat_response = await self._completion_service.function_call_async(
                messages=llm_input_messages,
                tools=self._get_tool_descriptions_for_llm(),
                tool_choice=tool_choice,
                structured_output_tool=output_tool_description,
            )

            span.set_attributes({
                SpanAttributes.LLM_OUTPUT_MESSAGES: json.dumps(chat_response.choices[0].message.model_dump()),
            })
            span.set_status(trace_api.StatusCode.OK)

            all_tool_calls = chat_response.choices[0].message.tool_calls

            if not all_tool_calls:
                self.log_trace_event("No tool calls found in the response. Returning the chat response.")
                imgs = get_images_from_message(history_messages_handled)

                artifacts = (
                    dict(agent_input.artifacts) if hasattr(agent_input, "artifacts") and agent_input.artifacts else {}
                )

                response_content = chat_response.choices[0].message.content or ""
                # TODO Make sources a first-class typed output (instead of going through artifacts)
                if "sources" in artifacts and artifacts["sources"]:
                    sourced_response = SourcedResponse(
                        response=response_content,
                        sources=artifacts["sources"],
                        is_successful=True,
                    )
                    filtered_response = self._formatter._renumber_sources(sourced_response)
                    artifacts["sources"] = filtered_response.sources
                    response_content = filtered_response.response

                    if filtered_response.sources:
                        original_retrieval_ranks, original_reranker_ranks = extract_source_ranks(
                            filtered_response.sources
                        )
                        span.set_attributes({
                            "original_retrieval_rank": json.dumps(original_retrieval_ranks),
                            "original_reranker_rank": json.dumps(original_reranker_ranks),
                        })

                if imgs:
                    artifacts["images"] = imgs
                else:
                    LOGGER.debug("No images found in the response.")
                return AgentPayload(
                    messages=[ChatMessage(role="assistant", content=response_content)],
                    is_final=True,
                    artifacts=artifacts,
                )

        agent_outputs, processed_tool_calls = await self._process_tool_calls(
            original_agent_input,
            tool_calls=all_tool_calls,
            ctx=ctx,
        )

        collected_artifacts = _collect_output_artifacts(agent_outputs)

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

        agent_input.artifacts.update(collected_artifacts)

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

            if collected_artifacts:
                final_output.artifacts.update(collected_artifacts)
            return final_output

        elif self._current_iteration + 1 < self._max_iterations:
            self.log_trace_event(
                message=(f"Number of successful tool outputs: {successful_output_count}. Running the agent again.")
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

            return AgentPayload(
                messages=[ChatMessage(role="assistant", content=DEFAULT_FALLBACK_REACT_ANSWER)],
                is_final=False,
            )

    # --- Thin adapter to typed I/O ---
    async def _run_without_io_trace(self, inputs: AIAgentInputs, ctx: dict) -> AIAgentOutputs:
        # Map typed inputs to the original call style
        initial_prompt = inputs.initial_prompt or INITIAL_PROMPT
        output_format = inputs.output_format
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
        outputs = AIAgentOutputs(
            output=final_message.content or "",
            full_message=final_message,
            is_final=core_result.is_final,
            artifacts=core_result.artifacts or {},
        )

        merge_constrained_output_to_root(outputs, final_message.content, output_format)

        return outputs


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


def _collect_output_artifacts(agent_outputs: dict[str, AgentPayload]) -> dict[str, Any]:
    # TODO: Refactor to use typed approach instead of dict-based artifacts

    collected_artifacts = {}
    all_sources = []

    for tool_call_id, agent_output in agent_outputs.items():
        if agent_output.artifacts:
            if "sources" in agent_output.artifacts:
                sources = agent_output.artifacts["sources"]
                all_sources.extend(sources)

            for key, value in agent_output.artifacts.items():
                if key != "sources":
                    collected_artifacts[key] = value

    if all_sources:
        collected_artifacts["sources"] = all_sources

    return collected_artifacts
