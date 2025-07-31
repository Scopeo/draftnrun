from typing import Optional

from openinference.semconv.trace import SpanAttributes
from opentelemetry.trace import get_current_span

from engine.agent.types import AgentPayload, ChatMessage, ComponentAttributes, ToolDescription
from engine.agent.agent import Agent
from engine.llm_services.llm_service import OCRService
from engine.trace.trace_manager import TraceManager
from engine.trace.serializer import serialize_to_json


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

    async def _run_without_io_trace(self, *input_payloads: AgentPayload | dict) -> AgentPayload:

        for payload in input_payloads:
            payload_json = (
                payload.model_dump(exclude_unset=True, exclude_none=True)
                if isinstance(payload, AgentPayload)
                else payload
            )

            span = get_current_span()
            span.set_attributes(
                {
                    SpanAttributes.INPUT_VALUE: serialize_to_json(payload_json, shorten_string=True),
                    SpanAttributes.LLM_MODEL_NAME: self._ocr_service._model_name,
                }
            )
            response = await self._ocr_service.get_ocr_text_async(payload_json)
            span.set_attributes(
                {
                    SpanAttributes.OUTPUT_VALUE: serialize_to_json(response),
                }
            )
            return AgentPayload(
                messages=[ChatMessage(role="assistant", content=response)],
            )
