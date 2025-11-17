import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Type

from openinference.semconv.trace import OpenInferenceSpanKindValues, SpanAttributes
from opentelemetry import trace as trace_api
from opentelemetry.util.types import Attributes
from pydantic import BaseModel, ValidationError
from tenacity import RetryError

from engine import legacy_compatibility
from engine.coercion_matrix import CoercionError
from engine.components.types import (
    AgentPayload,
    ChatMessage,
    ComponentAttributes,
    NodeData,
    ToolDescription,
)
from engine.prometheus_metric import track_calls
from engine.trace.serializer import serialize_to_json
from engine.trace.trace_manager import TraceManager

LOGGER = logging.getLogger(__name__)


class Component(ABC):
    TRACE_SPAN_KIND: str = OpenInferenceSpanKindValues.AGENT.value
    # NOTE: Flag for retro-compatibility with legacy components
    # TODO: Remove flag and retro-compatibility with legacy components
    # after all components are migrated
    migrated: bool = False

    def __init__(
        self,
        trace_manager: TraceManager,
        tool_description: ToolDescription,
        component_attributes: ComponentAttributes,
        **kwargs,
    ):
        self.trace_manager = trace_manager
        self.tool_description = tool_description
        self.component_attributes = component_attributes

        self._trace_attributes: dict[str, Any] = {}
        self._trace_events: list[str] = []

    @classmethod
    def get_inputs_schema(cls) -> Type[BaseModel]:
        class DefaultInput(BaseModel):
            input: Any

        return DefaultInput

    @classmethod
    def get_outputs_schema(cls) -> Type[BaseModel]:
        class DefaultOutput(BaseModel):
            output: Any

        return DefaultOutput

    @classmethod
    def get_canonical_ports(cls) -> Dict[str, Optional[str]]:
        """Logic to define default ports for simple A->B connections"""
        return {"input": "input", "output": "output"}

    @abstractmethod
    async def _run_without_io_trace(self, inputs: BaseModel, ctx: Dict[str, Any]) -> BaseModel:
        """Core execution method for agent logic.

        Args:
            inputs: Validated input data as a Pydantic model
            ctx: Runtime context such as template variables, file data, and execution state

        Returns:
            Pydantic model instance matching the declared output type
        """
        pass

    def log_trace(
        self,
        attributes: dict[str, Attributes],
    ) -> None:
        """Can be used to log additional trace attributes"""
        if not attributes:
            raise ValueError("Attributes must be provided to log_trace")
        self._trace_attributes.update(attributes)

    def log_trace_event(
        self,
        message: str,
    ) -> None:
        """Can be used to log additional trace events"""
        if not message:
            raise ValueError("Message must be provided to log_trace_event")
        self._trace_events.append(message)

    def _set_trace_data(self, span: trace_api.Span) -> None:
        """Set the cumulative trace attributes on the span and reset the trace attributes"""
        span.set_attributes(self._trace_attributes)
        for event in self._trace_events:
            span.add_event(event)

        self._trace_attributes = {}
        self._trace_events = []

    # Legacy adapter; subclasses with legacy signature do not need to override this.
    # TODO: Remove after I/O refactor migration
    async def _legacy_run_without_io_trace(self, *inputs: AgentPayload | dict, **kwargs) -> AgentPayload:
        raise NotImplementedError("Legacy components must implement this method or keep old signature with adapter.")

    @track_calls
    async def run(self, *args, **kwargs):
        # Dispatcher supporting both NodeData and legacy AgentPayload calls
        input_node_data: Optional[NodeData] = None
        if len(args) == 1 and isinstance(args[0], NodeData):
            input_node_data = args[0]

        span_name = self.component_attributes.component_instance_name
        with self.trace_manager.start_span(span_name) as span:
            try:
                if input_node_data is not None:
                    span.set_attributes({
                        SpanAttributes.OPENINFERENCE_SPAN_KIND: self.TRACE_SPAN_KIND,
                        SpanAttributes.INPUT_VALUE: serialize_to_json(input_node_data.data, shorten_string=True),
                        "component_instance_id": (
                            str(self.component_attributes.component_instance_id)
                            if self.component_attributes.component_instance_id is not None
                            else None
                        ),
                    })
                    if self.tool_description.is_tool:
                        span.set_attributes({
                            SpanAttributes.TOOL_NAME: self.tool_description.name,
                            SpanAttributes.TOOL_DESCRIPTION: self.tool_description.description,
                            SpanAttributes.TOOL_PARAMETERS: serialize_to_json(
                                input_node_data.data, shorten_string=True
                            ),
                        })

                    if self.migrated:
                        InputModel = self.get_inputs_schema()
                        validated_inputs = InputModel(**input_node_data.data)
                        output_model_instance = await self._run_without_io_trace(
                            inputs=validated_inputs, ctx=input_node_data.ctx
                        )
                        OutputModel = self.get_outputs_schema()
                        if not isinstance(output_model_instance, OutputModel):
                            raise TypeError(
                                f"Component returned type {type(output_model_instance).__name__}, "
                                f"but expected {OutputModel.__name__}"
                            )
                        output_node_data = NodeData(data=output_model_instance.model_dump(), ctx=input_node_data.ctx)
                        span.set_attributes({
                            SpanAttributes.OUTPUT_VALUE: serialize_to_json(output_node_data.data, shorten_string=True)
                        })
                        self._set_trace_data(span)
                        span.set_status(trace_api.StatusCode.OK)
                        return output_node_data
                    else:
                        data = input_node_data.data or {}
                        if "messages" in data:
                            legacy_arg = AgentPayload(**data)
                        else:
                            content = data.get("input")
                            if isinstance(content, str):
                                legacy_arg = AgentPayload(messages=[ChatMessage(role="user", content=content)])
                            elif isinstance(content, list):
                                legacy_arg = {"messages": content}
                            else:
                                legacy_arg = AgentPayload(messages=[])
                        legacy_output = await self._run_without_io_trace(legacy_arg, ctx=input_node_data.ctx)
                        output_node_data = legacy_compatibility.convert_legacy_to_node_data(
                            legacy_output, input_node_data.ctx
                        )
                        span.set_attributes({
                            SpanAttributes.OUTPUT_VALUE: serialize_to_json(output_node_data.data, shorten_string=True)
                        })
                        self._set_trace_data(span)
                        span.set_status(trace_api.StatusCode.OK)
                        return output_node_data

                # Legacy invocation path (GraphRunner/tools)
                legacy_input_preview = None
                if args:
                    legacy_input_preview = args[0]
                elif kwargs:
                    legacy_input_preview = kwargs
                span.set_attributes({
                    SpanAttributes.OPENINFERENCE_SPAN_KIND: self.TRACE_SPAN_KIND,
                    SpanAttributes.INPUT_VALUE: serialize_to_json(legacy_input_preview, shorten_string=True),
                    "component_instance_id": (
                        str(self.component_attributes.component_instance_id)
                        if self.component_attributes.component_instance_id is not None
                        else None
                    ),
                })
                if self.tool_description.is_tool:
                    span.set_attributes({
                        SpanAttributes.TOOL_NAME: self.tool_description.name,
                        SpanAttributes.TOOL_DESCRIPTION: self.tool_description.description,
                    })

                if self.migrated:
                    InputModel = self.get_inputs_schema()
                    # Extract ctx from kwargs so it is not treated as an input field
                    ctx = kwargs.pop("ctx", {})
                    data = legacy_compatibility.collect_inputs_from_legacy(args, kwargs)

                    ports = self.get_canonical_ports()
                    input_port_name = ports.get("input")
                    if (
                        input_port_name
                        and input_port_name not in data
                        and "messages" in data
                        and isinstance(data["messages"], list)
                        and data["messages"]
                    ):
                        # Transform legacy messages to component input field
                        last_message = data["messages"][-1]
                        if isinstance(last_message, ChatMessage):
                            data[input_port_name] = last_message.content or ""
                        elif isinstance(last_message, dict):
                            data[input_port_name] = last_message.get("content", "")

                    try:
                        validated_inputs = InputModel(**data)
                    except ValidationError as e:
                        component_name = self.component_attributes.component_instance_name or self.__class__.__name__
                        raise CoercionError(
                            source_type=type(data),
                            target_type=InputModel,
                            value=data,
                            reason=f"Failed to validate inputs for component '{component_name}': {e}",
                        ) from e
                    # Pass ctx that was explicitly provided by caller (e.g., ReActAgent)
                    output_model_instance = await self._run_without_io_trace(inputs=validated_inputs, ctx=ctx)
                    OutputModel = self.get_outputs_schema()
                    if not isinstance(output_model_instance, OutputModel):
                        raise TypeError(
                            f"Component returned type {type(output_model_instance).__name__}, "
                            f"but expected {OutputModel.__name__}"
                        )
                    legacy_output = legacy_compatibility.convert_typed_output_to_legacy(output_model_instance)
                else:
                    legacy_output = await self._run_without_io_trace(*args, **kwargs)

                span.set_attributes({
                    SpanAttributes.OUTPUT_VALUE: serialize_to_json(legacy_output, shorten_string=True)
                })
                self._set_trace_data(span)
                span.set_status(trace_api.StatusCode.OK)
                return legacy_output

            except RetryError as e:
                LOGGER.exception(
                    f"Error running {self.tool_description.name} Last attempt: {e.last_attempt.exception()}"
                )
                span.set_status(trace_api.StatusCode.ERROR)
                span.record_exception(e.last_attempt.exception())
                raise e.last_attempt.exception()
            except Exception as e:
                LOGGER.exception(f"Error running {self.tool_description.name}: {e}")
                span.set_status(trace_api.StatusCode.ERROR)
                span.record_exception(e)
                raise e

    def run_sync(self, *inputs, **kwargs):
        return asyncio.run(self.run(*inputs, **kwargs))
