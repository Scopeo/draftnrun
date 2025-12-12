from collections.abc import Callable
from typing import Optional, Any, Type
from pydantic import BaseModel, Field
import logging

from openinference.semconv.trace import SpanAttributes
from opentelemetry.trace import get_current_span

from engine.agent.agent import Agent
from engine.agent.types import ChatMessage, ToolDescription, ComponentAttributes
from engine.agent.utils import parse_openai_message_format
from engine.agent.utils_prompt import fill_prompt_template
from engine.llm_services.llm_service import CompletionService
from engine.trace.trace_manager import TraceManager
from engine.trace.serializer import serialize_to_json

LOGGER = logging.getLogger(__name__)

DEFAULT_LLM_CALL_TOOL_DESCRIPTION = ToolDescription(
    name="LLM Call",
    description="Templated LLM Call",
    tool_properties={
        "messages": {
            "type": "array",
            "description": "A list of messages containing fixed text and a file.",
            "minItems": 1,
            "items": {
                "type": "object",
                "properties": {
                    "role": {"type": "string", "const": "user"},
                    "content": {
                        "type": "array",
                        "description": "First item is fixed text, second is a file.",
                        "minItems": 1,
                        "maxItems": 2,
                        "items": {
                            "type": "object",
                            "properties": {
                                "type": {"type": "string", "enum": ["text", "file"]},
                                "text": {"type": "string"},
                                "file": {
                                    "type": "object",
                                    "properties": {
                                        "file_data": {
                                            "type": "string",
                                            "description": "Base64-encoded file content with MIME prefix.",
                                        },
                                        "file_url": {
                                            "type": "string",
                                            "description": "URL to the file for OpenAI API.",
                                        },
                                    },
                                    "required": ["file_data", "file_url"],
                                },
                            },
                            "required": ["type"],
                        },
                    },
                },
                "required": ["role", "content"],
            },
        }
    },
    required_tool_properties=["messages"],
)


class LLMCallInputs(BaseModel):
    messages: list[ChatMessage] = Field(
        description="The input messages",
    )
    prompt_template: Optional[str] = Field(
        default=None,
        description="Prompt template to use for the LLM call.",
        json_schema_extra={"disabled_as_input": True},
    )
    output_format: Optional[dict[str, Any]] = Field(
        default=None,
        description="Structured output format.",
        json_schema_extra={"disabled_as_input": True},
    )
    # Allow extra fields for backward compatibility
    model_config = {"extra": "allow"}


class LLMCallOutputs(BaseModel):
    output: str = Field(description="The LLM response")
    artifacts: dict[str, Any] = Field(default_factory=dict)


class LLMCallAgent(Agent):
    migrated = True

    # Add schema methods
    @classmethod
    def get_inputs_schema(cls) -> Type[BaseModel]:
        return LLMCallInputs

    @classmethod
    def get_outputs_schema(cls) -> Type[BaseModel]:
        return LLMCallOutputs

    @classmethod
    def get_canonical_ports(cls) -> dict[str, str | None]:
        return {"input": "messages", "output": "output"}

    def __init__(
        self,
        trace_manager: TraceManager,
        completion_service: CompletionService,
        tool_description: ToolDescription,
        component_attributes: ComponentAttributes,
        prompt_template: str,
        capability_resolver: Callable[[list[str]], set[str]],
        file_content_key: Optional[str] = None,
        file_url_key: Optional[str] = None,
        output_format: Optional[dict[str] | None] = None,
    ):
        super().__init__(
            trace_manager=trace_manager,
            tool_description=tool_description,
            component_attributes=component_attributes,
        )
        self._completion_service = completion_service
        self._prompt_template = prompt_template
        self._file_content_key = file_content_key
        self._file_url_key = file_url_key
        self.output_format = output_format
        self._capability_resolver = capability_resolver

    def _extract_file_content(self, inputs: LLMCallInputs, ctx: Optional[dict]) -> list:
        """Extract file content from inputs or ctx and return as a list."""
        if not self._file_content_key:
            return []

        input_dict = inputs.model_dump(exclude_none=True)
        file_data = None
        if self._file_content_key in input_dict:
            file_data = input_dict[self._file_content_key]
        elif ctx is not None and self._file_content_key in ctx:
            file_data = ctx[self._file_content_key]

        if isinstance(file_data, dict) and "filename" in file_data and "file_data" in file_data:
            return [{"type": "file", "file": file_data}]
        return []

    def _extract_file_url(self, inputs: LLMCallInputs, ctx: Optional[dict]) -> list:
        """Extract file URL from inputs or ctx and return as a list."""
        if not self._file_url_key:
            return []

        input_dict = inputs.model_dump(exclude_none=True)
        file_url = None
        if self._file_url_key in input_dict:
            file_url = input_dict[self._file_url_key]
        elif ctx is not None and self._file_url_key in ctx:
            file_url = ctx[self._file_url_key]

        if isinstance(file_url, str) and file_url:
            return [{"type": "file", "file_url": file_url}]
        return []

    async def _run_without_io_trace(self, inputs: LLMCallInputs, ctx: Optional[dict] = None) -> LLMCallOutputs:
        LOGGER.info(f"Running LLM call agent with inputs: {inputs} and ctx: {ctx}")
        prompt_template = inputs.prompt_template or self._prompt_template
        output_format = inputs.output_format or self.output_format

        files_content = []
        images_content = []

        input_from_messages = ""
        if inputs.messages:
            last_message = inputs.messages[-1]
            if last_message.content:
                text_content, payload_files_content, payload_images_content = parse_openai_message_format(
                    last_message.content
                )
                input_from_messages = text_content
                files_content.extend(payload_files_content)
                images_content.extend(payload_images_content)

        input_dict = inputs.model_dump(exclude_none=True)
        input_dict["input"] = input_from_messages

        merged_dict = {**(ctx or {}), **input_dict}

        text_content = fill_prompt_template(
            prompt_template=prompt_template,
            component_name=self.component_attributes.component_instance_name,
            variables=merged_dict,
        )

        files_content.extend(self._extract_file_content(inputs, ctx))
        files_content.extend(self._extract_file_url(inputs, ctx))

        file_supported_references = self._resolve_capabilities(["file"])

        if (
            len(files_content) > 0
            and f"{self._completion_service._provider}:{self._completion_service._model_name}"
            not in file_supported_references
        ):
            raise ValueError(f"File content is not supported for provider '{self._completion_service._provider}'.")

        image_supported_references = self._resolve_capabilities(["image"])

        if (
            len(images_content) > 0
            and f"{self._completion_service._provider}:{self._completion_service._model_name}"
            not in image_supported_references
        ):
            raise ValueError(f"Image content is not supported for provider '{self._completion_service._provider}'.")

        if len(files_content) > 0 or len(images_content) > 0:
            content = [
                {
                    "type": "text",
                    "text": text_content,
                },
                *files_content,
                *images_content,
            ]
        else:
            content = text_content

        span = get_current_span()
        span.set_attributes(
            {
                SpanAttributes.INPUT_VALUE: serialize_to_json(
                    [{"role": "user", "content": content}], shorten_string=True
                ),
                SpanAttributes.LLM_MODEL_NAME: self._completion_service._model_name,
                "model_id": (
                    str(self._completion_service._model_id) if self._completion_service._model_id is not None else None
                ),
            }
        )
        if output_format:
            response = await self._completion_service.constrained_complete_with_json_schema_async(
                messages=[{"role": "user", "content": content}],
                response_format=output_format,
            )
        else:
            response = await self._completion_service.complete_async(
                messages=[{"role": "user", "content": content}],
            )
        return LLMCallOutputs(output=response, artifacts={})

    def _resolve_capabilities(self, capabilities: list[str]) -> set[str]:
        return self._capability_resolver(capabilities)
