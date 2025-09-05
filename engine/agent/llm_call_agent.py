from typing import Optional

from openinference.semconv.trace import SpanAttributes
from opentelemetry.trace import get_current_span

from engine.agent.agent import Agent
from engine.agent.types import AgentPayload, ChatMessage, ToolDescription, ComponentAttributes
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
                                        }
                                    },
                                    "required": ["file_data"],
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


class LLMCallAgent(Agent):
    def __init__(
        self,
        trace_manager: TraceManager,
        completion_service: CompletionService,
        tool_description: ToolDescription,
        component_attributes: ComponentAttributes,
        prompt_template: str,
        file_content_key: Optional[str] = None,
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
        self.output_format = output_format

    async def _run_without_io_trace(self, *input_payloads: AgentPayload | dict, **kwargs) -> AgentPayload:
        prompt_vars = extract_vars_in_text_template(self._prompt_template)
        input_replacements = {}
        files_content = []
        images_content = []

        if kwargs:
            input_payloads = [kwargs]

        input_replacements["input"] = ""
        for payload in input_payloads:
            payload_json = (
                payload.model_dump(exclude_unset=True, exclude_none=True)
                if isinstance(payload, AgentPayload)
                else payload
            )
            if (
                "messages" in payload_json
                and payload_json["messages"]
                and "content" in payload_json["messages"][-1]
                and payload_json["messages"][-1]["content"]
            ):
                text_content, payload_files_content, payload_images_content = parse_openai_message_format(
                    payload_json["messages"][-1]["content"], self._completion_service._provider
                )
                input_replacements["input"] += text_content
                files_content.extend(payload_files_content)
                images_content.extend(payload_images_content)

        for prompt_var in prompt_vars:
            for payload in input_payloads:
                if prompt_var in payload_json:
                    input_replacements[prompt_var] = payload_json[prompt_var]
                    continue
            if prompt_var not in input_replacements:
                input_replacements[prompt_var] = ""

        if self._file_content_key:
            for payload in input_payloads:
                if (
                    self._file_content_key in payload_json
                    and isinstance(payload_json[self._file_content_key], dict)
                    and "filename" in payload_json[self._file_content_key]
                    and "file_data" in payload_json[self._file_content_key]
                ):
                    files_content.append({"type": "file", "file": payload_json[self._file_content_key]})
                    continue

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
        return AgentPayload(
            messages=[ChatMessage(role="assistant", content=response)],
        )
