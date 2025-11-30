import logging
import json
import string
from typing import Optional, Dict, Any, Union

import httpx
from openinference.semconv.trace import OpenInferenceSpanKindValues

from engine.agent.agent import Agent
from engine.agent.types import (
    ChatMessage,
    AgentPayload,
    ComponentAttributes,
    ToolDescription,
)
from engine.agent.utils import load_str_to_json
from engine.trace.trace_manager import TraceManager

LOGGER = logging.getLogger(__name__)

API_CALL_TOOL_DESCRIPTION = ToolDescription(
    name="api_call",
    description=("A generic API tool that can make HTTP requests to any API endpoint."),
    tool_properties={
        "query_param1": {
            "type": "string",
            "description": ("This the first query parameter to be sent to the API. "),
        },
        "query_param2": {
            "type": "string",
            "description": ("This the second query parameter to be sent to the API."),
        },
    },
    required_tool_properties=[],
)


class APICallTool(Agent):
    TRACE_SPAN_KIND = OpenInferenceSpanKindValues.TOOL.value

    def __init__(
        self,
        trace_manager: TraceManager,
        component_attributes: ComponentAttributes,
        endpoint: str,
        method: str = "GET",
        headers: Optional[Union[Dict[str, Any], str]] = None,
        timeout: int = 30,
        allowed_domains: Optional[str] = None,
        fixed_parameters: Optional[Union[Dict[str, Any], str]] = None,
        tool_description: ToolDescription = API_CALL_TOOL_DESCRIPTION,
    ) -> None:
        super().__init__(
            trace_manager=trace_manager,
            tool_description=tool_description,
            component_attributes=component_attributes,
        )
        self.trace_manager = trace_manager
        self.endpoint = endpoint
        self.method = method.upper()
        if isinstance(headers, str):
            self.headers = load_str_to_json(headers) if headers else {}
        else:
            self.headers = headers or {}
        self.timeout = timeout
        self.allowed_domains = allowed_domains
        if isinstance(fixed_parameters, str):
            self.fixed_parameters = load_str_to_json(fixed_parameters) if fixed_parameters else {}
        else:
            self.fixed_parameters = fixed_parameters or {}

    async def make_api_call(self, **kwargs) -> Dict[str, Any]:
        """Make an HTTP request to the configured API endpoint."""

        request_headers = self.headers.copy()

        all_parameters = self.fixed_parameters.copy()
        all_parameters.update(kwargs)
        endpoint = self.endpoint.format(**all_parameters)
        formatter = string.Formatter()
        used_keys = {field_name for _, field_name, _, _ in formatter.parse(self.endpoint) if field_name}
        filtered_parameters = {key: value for key, value in all_parameters.items() if key not in used_keys}

        request_kwargs = {
            "url": endpoint,
            "method": self.method,
            "headers": request_headers,
            "timeout": self.timeout,
        }

        # Handle parameters based on HTTP method
        if self.method in [
            "GET",
            "DELETE",
        ]:
            if filtered_parameters:
                request_kwargs["params"] = filtered_parameters
        elif self.method in [
            "POST",
            "PUT",
            "PATCH",
        ]:
            request_kwargs["json"] = filtered_parameters

        try:
            async with httpx.AsyncClient() as client:
                response = await client.request(**request_kwargs)
                response.raise_for_status()

                # Try to parse JSON response, fall back to text
                try:
                    response_data = response.json()
                except ValueError:
                    response_data = {"text": response.text}

                return {
                    "status_code": response.status_code,
                    "data": response_data,
                    "headers": dict(response.headers),
                    "success": True,
                }

        except httpx.HTTPError as e:
            LOGGER.error(f"API request failed: {str(e)}")
            return {
                "status_code": (getattr(e.response, "status_code", None) if hasattr(e, "response") else None),
                "error": str(e),
                "success": False,
            }

    async def _run_without_io_trace(
        self,
        *inputs: AgentPayload,
        ctx: Optional[dict] = None,
        **kwargs: Any,
    ) -> AgentPayload:
        # Make the API call
        api_response = await self.make_api_call(**kwargs)

        # Format the API response as a readable message
        if api_response.get("success", False):
            content = json.dumps(api_response["data"], indent=2)
        else:
            content = f"API call failed: {api_response.get('error', 'Unknown error')}"

        return AgentPayload(
            messages=[ChatMessage(role="assistant", content=content)],
            artifacts={"api_response": api_response},
            is_final=False,
        )
