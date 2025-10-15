from typing import Optional, Any, Type
from pydantic import BaseModel, Field

from openinference.semconv.trace import SpanAttributes
from opentelemetry.trace import get_current_span

from engine.agent.agent import Agent
from engine.agent.types import ChatMessage, ToolDescription, ComponentAttributes
from engine.agent.utils import extract_vars_in_text_template, parse_openai_message_format
from engine.llm_services.llm_service import CompletionService
from engine.trace.trace_manager import TraceManager
from engine.trace.serializer import serialize_to_json
from ada_backend.database.seed.supported_models import (
    get_models_by_capability,
    ModelCapability,
)

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
    messages: list[ChatMessage] = Field(description="The input messages")
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

    async def _run_without_io_trace(self, inputs: LLMCallInputs, ctx: dict) -> LLMCallOutputs:
        # Extract template vars from context
        template_vars = ctx.get("template_vars", {})

        prompt_vars = extract_vars_in_text_template(self._prompt_template)
        input_replacements = {}
        files_content = []
        images_content = []

        # Extract input from messages
        input_replacements["input"] = ""
        if inputs.messages:
            last_message = inputs.messages[-1]
            if last_message.content:
                text_content, payload_files_content, payload_images_content = parse_openai_message_format(
                    last_message.content, self._completion_service._provider
                )
                input_replacements["input"] = text_content
                files_content.extend(payload_files_content)
                images_content.extend(payload_images_content)

        # Fill template vars from context
        for prompt_var in prompt_vars:
            if prompt_var in template_vars:
                input_replacements[prompt_var] = template_vars[prompt_var]
            elif prompt_var not in input_replacements:
                raise ValueError(
                    f"Missing template variable '{prompt_var}' needed in prompt template "
                    f"of component '{self.component_attributes.component_instance_name}'. "
                    f"Available template vars: {list(template_vars.keys())}"
                )

        # Handle file content from context
        file_content_ctx = ctx.get("file_content", {})
        if self._file_content_key and self._file_content_key in file_content_ctx:
            file_data = file_content_ctx[self._file_content_key]
            if isinstance(file_data, dict) and "filename" in file_data and "file_data" in file_data:
                files_content.append({"type": "file", "file": file_data})

        # Handle file URLs from context
        file_urls_ctx = ctx.get("file_urls", {})
        if self._file_url_key and self._file_url_key in file_urls_ctx:
            file_url = file_urls_ctx[self._file_url_key]
            files_content.append({"type": "file", "file_url": file_url})

        text_content = self._prompt_template.format(**input_replacements)

        # Check for file support
        file_supported_references = [
            model_reference["reference"] for model_reference in get_models_by_capability(ModelCapability.FILE)
        ]
        if (
            len(files_content) > 0
            and f"{self._completion_service._provider}:{self._completion_service._model_name}"
            not in file_supported_references
        ):
            raise ValueError(f"File content is not supported for provider '{self._completion_service._provider}'.")

        # Check for image support
        image_supported_references = [
            model_reference["reference"] for model_reference in get_models_by_capability(ModelCapability.IMAGE)
        ]
        if (
            len(images_content) > 0
            and f"{self._completion_service._provider}:{self._completion_service._model_name}"
            not in image_supported_references
        ):
            raise ValueError(f"Image content is not supported for provider '{self._completion_service._provider}'.")

        # Build content based on what's present
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
            }
        )
        if self.output_format:
            response = await self._completion_service.constrained_complete_with_json_schema_async(
                messages=[{"role": "user", "content": content}],
                response_format=self.output_format,
            )
        else:
            response = await self._completion_service.complete_async(
                messages=[{"role": "user", "content": content}],
            )
        return LLMCallOutputs(output=response, artifacts={})
