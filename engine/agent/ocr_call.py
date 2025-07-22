from typing import Optional

from openinference.semconv.trace import SpanAttributes
from opentelemetry.trace import get_current_span

from engine.agent.agent import Agent, AgentPayload, ChatMessage, ComponentAttributes, ToolDescription
from engine.llm_services.llm_service import OCRService
from engine.trace.trace_manager import TraceManager


class OCRCall(Agent):
    def __init__(
        self,
        trace_manager: TraceManager,
        ocr_service: OCRService,
        tool_description: ToolDescription,
        component_attributes: ComponentAttributes,
        file_content: Optional[str] = None,
    ):
        super().__init__(
            trace_manager=trace_manager,
            tool_description=tool_description,
            component_attributes=component_attributes,
        )
        self._ocr_service = ocr_service
        self._file_content = file_content

    def _find_file_data(self, payload_json: dict) -> Optional[str]:

        if "messages" not in payload_json or not payload_json["messages"]:
            return None

        for message in reversed(payload_json["messages"]):
            if not isinstance(message, dict) or "content" not in message:
                continue

            content = message["content"]
            if not content:
                continue

            payload_json["messages"][-1]["content"] = content if isinstance(content, list) else [content]

            for content_item in payload_json["messages"][-1]["content"]:
                if (
                    isinstance(content_item, dict)
                    and "file" in content_item
                    and isinstance(content_item["file"], dict)
                    and "file_data" in content_item["file"]
                ):
                    return content_item["file"]["file_data"]

        return None

    async def _run_without_trace(self, *input_payloads: AgentPayload | dict) -> AgentPayload:

        for payload in input_payloads:
            payload_json = (
                payload.model_dump(exclude_unset=True, exclude_none=True)
                if isinstance(payload, AgentPayload)
                else payload
            )

            file_data = self._find_file_data(payload_json)

            if file_data:
                span = get_current_span()
                span.set_attributes(
                    {
                        SpanAttributes.LLM_MODEL_NAME: self._ocr_service._model_name,
                    }
                )
                response = await self._ocr_service.get_ocr_text_async(file_data)
                return AgentPayload(
                    messages=[ChatMessage(role="assistant", content=response)],
                )
            else:
                raise ValueError("No file data found for OCR processing. Provide file for OCR processing.")
