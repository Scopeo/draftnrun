from typing import Optional, Type

from openinference.semconv.trace import SpanAttributes
from opentelemetry.trace import get_current_span
from pydantic import BaseModel, Field

from engine.components.component import Component
from engine.components.types import ChatMessage, ComponentAttributes, ToolDescription
from engine.llm_services.llm_service import OCRService
from engine.trace.serializer import serialize_to_json
from engine.trace.trace_manager import TraceManager


class OCRCallInputs(BaseModel):
    messages: list[ChatMessage] = Field(
        default_factory=list,
        description="Messages containing file/image data for OCR processing",
    )
    model_config = {"extra": "allow"}


class OCRCallOutputs(BaseModel):
    output: str = Field(description="The extracted OCR text")


class OCRCall(Component):
    migrated = True

    @classmethod
    def get_inputs_schema(cls) -> Type[BaseModel]:
        return OCRCallInputs

    @classmethod
    def get_outputs_schema(cls) -> Type[BaseModel]:
        return OCRCallOutputs

    @classmethod
    def get_canonical_ports(cls) -> dict[str, str | None]:
        return {"input": "messages", "output": "output"}

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

    async def _run_without_io_trace(self, inputs: OCRCallInputs, ctx: Optional[dict] = None) -> OCRCallOutputs:
        messages_dict = {
            "messages": [msg.model_dump(exclude_unset=True, exclude_none=True) for msg in inputs.messages]
        }

        span = get_current_span()
        span.set_attributes({
            SpanAttributes.INPUT_VALUE: serialize_to_json(messages_dict, shorten_string=True),
            SpanAttributes.LLM_MODEL_NAME: self._ocr_service._model_name,
            "model_id": (str(self._ocr_service._model_id) if self._ocr_service._model_id is not None else None),
        })
        response = await self._ocr_service.get_ocr_text_async(messages_dict)
        span.set_attributes({
            SpanAttributes.OUTPUT_VALUE: serialize_to_json(response),
        })
        return OCRCallOutputs(output=response)
