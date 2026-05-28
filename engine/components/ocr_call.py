from typing import Callable, Optional, Type
from uuid import UUID

from openinference.semconv.trace import SpanAttributes
from opentelemetry.trace import get_current_span
from pydantic import BaseModel, Field

from ada_backend.database.models import ParameterType
from engine.components.component import Component
from engine.components.types import ChatMessage, ComponentAttributes, ToolDescription
from engine.constants import DEFAULT_MODEL_OCR
from engine.llm_services.llm_service import OCRService
from engine.llm_services.utils import get_llm_provider_and_model
from engine.trace.serializer import serialize_to_json
from engine.trace.trace_manager import TraceManager


class OCRCallInputs(BaseModel):
    completion_model: str = Field(
        default=DEFAULT_MODEL_OCR,
        json_schema_extra={
            "is_tool_input": False,
            "parameter_type": ParameterType.LLM_MODEL,
            "ui_component": "Select",
            "ui_component_properties": {"label": "Model Name", "model_capabilities": ["ocr"]},
        },
    )
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
        tool_description: ToolDescription,
        component_attributes: ComponentAttributes,
        llm_api_key: Optional[str] = None,
        model_id_resolver: Optional[Callable[[str], Optional[UUID]]] = None,
        file_content: Optional[str] = None,
    ):
        super().__init__(
            trace_manager=trace_manager,
            tool_description=tool_description,
            component_attributes=component_attributes,
        )
        self._llm_api_key = llm_api_key
        self._model_id_resolver = model_id_resolver or (lambda _: None)
        self._file_content = file_content

    async def _run_without_io_trace(self, inputs: OCRCallInputs, ctx: Optional[dict] = None) -> OCRCallOutputs:
        provider, model_name = get_llm_provider_and_model(inputs.completion_model)
        ocr_service = OCRService(
            trace_manager=self.trace_manager,
            provider=provider,
            model_name=model_name,
            api_key=self._llm_api_key,
            model_id=self._model_id_resolver(model_name),
        )

        messages_dict = {
            "messages": [msg.model_dump(exclude_unset=True, exclude_none=True) for msg in inputs.messages]
        }

        span = get_current_span()
        span.set_attributes({
            SpanAttributes.INPUT_VALUE: serialize_to_json(messages_dict, shorten_string=True),
            SpanAttributes.LLM_MODEL_NAME: ocr_service._model_name,
            "model_id": (str(ocr_service._model_id) if ocr_service._model_id is not None else None),
        })
        response = await ocr_service.get_ocr_text_async(messages_dict)
        span.set_attributes({
            SpanAttributes.OUTPUT_VALUE: serialize_to_json(response),
        })
        return OCRCallOutputs(output=response)
