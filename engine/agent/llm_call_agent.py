from typing import Optional

from openinference.semconv.trace import SpanAttributes
from opentelemetry.trace import get_current_span

from engine.agent.agent import Agent, AgentPayload, ChatMessage, ComponentAttributes, ToolDescription
from engine.agent.utils import extract_vars_in_text_template, parse_openai_message_format
from engine.llm_services.llm_service import CompletionService
from engine.trace.trace_manager import TraceManager
from engine.trace.serializer import serialize_to_json

FILE_SUPPORTED_PROVIDERS = ["openai"]
IMAGE_SUPPORTED_PROVIDERS = ["openai", "google"]


class LLMCallAgent(Agent):
    def __init__(
        self,
        trace_manager: TraceManager,
        completion_service: CompletionService,
        tool_description: ToolDescription,
        component_attributes: ComponentAttributes,
        prompt_template: str,
        file_content: Optional[str] = None,
        output_format: Optional[dict[str] | None] = None,
    ):
        super().__init__(
            trace_manager=trace_manager,
            tool_description=tool_description,
            component_attributes=component_attributes,
        )
        self._completion_service = completion_service
        self._prompt_template = prompt_template
        self._file_content = file_content
        self.output_format = output_format

    async def _run_without_trace(self, *input_payloads: AgentPayload | dict) -> AgentPayload:
        prompt_vars = extract_vars_in_text_template(self._prompt_template)
        input_replacements = {}
        files_content = []
        images_content = []

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

        file_content_vars = extract_vars_in_text_template(self._file_content) if self._file_content else []
        for file_var in file_content_vars:
            for payload in input_payloads:
                if (
                    file_var in payload_json
                    and isinstance(payload_json[file_var], dict)
                    and "filename" in payload_json[file_var]
                    and "file_data" in payload_json[file_var]
                ):
                    files_content.append({"type": "file", "file": payload_json[file_var]})
                    continue

        text_content = self._prompt_template.format(**input_replacements)

        if len(files_content) > 0:
            # TODO: Add support for other providers
            if self._completion_service._provider not in FILE_SUPPORTED_PROVIDERS:
                raise ValueError(f"File content is not supported for provider '{self._completion_service._provider}'.")
            content = [
                {
                    "type": "text",
                    "text": text_content,
                },
                *files_content,
            ]
        else:
            content = text_content

        if len(images_content) > 0:
            # TODO: Add support for other providers
            if self._completion_service._provider not in IMAGE_SUPPORTED_PROVIDERS:
                raise ValueError(
                    f"Image content is not supported for provider '{self._completion_service._provider}'."
                )
            content = [
                {
                    "type": "text",
                    "text": text_content,
                },
                *images_content,
            ]
        else:
            content = text_content

        span = get_current_span()
        span.set_attributes(
            {
                SpanAttributes.INPUT_VALUE: serialize_to_json([{"role": "user", "content": content}]),
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
