import asyncio
import logging
import json
from abc import ABC, abstractmethod
from typing import Any

from openinference.semconv.trace import OpenInferenceSpanKindValues, SpanAttributes
from opentelemetry import trace as trace_api
from opentelemetry.util.types import Attributes
from tenacity import RetryError

from engine.agent.data_structures import AgentPayload, ToolDescription
from engine.agent.utils import convert_data_for_trace_manager_display
from engine.trace.trace_manager import TraceManager
from engine.prometheus_metric import track_calls

LOGGER = logging.getLogger(__name__)


class Agent(ABC):
    TRACE_SPAN_KIND: str = OpenInferenceSpanKindValues.AGENT.value

    def __init__(
        self,
        trace_manager: TraceManager,
        tool_description: ToolDescription,
        component_instance_name: str,
        **kwargs,
    ):
        self.trace_manager = trace_manager
        self.tool_description = tool_description
        self.component_instance_name = component_instance_name

        self._trace_attributes: dict[str, Any] = {}
        self._trace_events: list[str] = []

    @abstractmethod
    async def _run_without_io_trace(self, *inputs: AgentPayload, **kwargs) -> AgentPayload:
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

    # TODO: Refactor Agent I/O to use an unified input/output object:
    # - Allow for multiple named inputs and outputs
    # - Keep message history
    @track_calls
    async def run(
        self,
        *inputs: AgentPayload | dict,
        **kwargs,
    ) -> AgentPayload | list[AgentPayload]:
        """
        Run the agent with the given inputs and kwargs.

        Args:
            *inputs: AgentInput - The inputs to the agent, can be multiple
            The first input is considered the main input and is used for tracing
            **kwargs: Any - Keyword arguments that are used for the tool call (function calling)

        Returns:
            AgentOutput: The output of the agent. Only one output it's allowed.
        """
        span_name = self.component_instance_name
        with self.trace_manager.start_span(span_name) as span:
            trace_input = convert_data_for_trace_manager_display(*inputs)
            span.set_attributes(
                {
                    SpanAttributes.OPENINFERENCE_SPAN_KIND: self.TRACE_SPAN_KIND,
                    SpanAttributes.INPUT_VALUE: trace_input,
                }
            )
            if self.tool_description.is_tool:
                span.set_attributes(
                    {
                        SpanAttributes.TOOL_NAME: self.tool_description.name,
                        SpanAttributes.TOOL_DESCRIPTION: self.tool_description.description,
                        SpanAttributes.TOOL_PARAMETERS: json.dumps(kwargs),
                    }
                )
            try:
                agent_output = await self._run_without_io_trace(*inputs, **kwargs)
                span.set_attributes(
                    {
                        SpanAttributes.OUTPUT_VALUE: agent_output.content,
                    }
                )

                self._set_trace_data(span)
                span.set_status(trace_api.StatusCode.OK)
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

            return agent_output

    def run_sync(self, *inputs: AgentPayload, **kwargs) -> AgentPayload | list[AgentPayload]:
        return asyncio.run(self.run(*inputs, **kwargs))
