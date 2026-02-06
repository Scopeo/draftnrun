import json
import logging
import string
from typing import Any, Dict, Optional, Type, Union

import httpx
from openinference.semconv.trace import OpenInferenceSpanKindValues
from pydantic import BaseModel, ConfigDict, Field

from engine.components.component import Component
from engine.components.types import (
    ComponentAttributes,
    ToolDescription,
)
from engine.components.utils import load_str_to_json
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


class APICallToolInputs(BaseModel):
    request_body: Optional[Any] = Field(
        default=None,
        description="Data to send in the API request body or as query parameters",
    )
    model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True)


class APICallToolOutputs(BaseModel):
    output: str = Field(description="The formatted API response or error message.")
    artifacts: dict[str, Any] = Field(
        default_factory=dict,
        description="Raw API response including status_code, data, headers, success flag.",
    )


class APICallTool(Component):
    TRACE_SPAN_KIND = OpenInferenceSpanKindValues.TOOL.value
    migrated = True

    @classmethod
    def get_inputs_schema(cls) -> Type[BaseModel]:
        return APICallToolInputs

    @classmethod
    def get_outputs_schema(cls) -> Type[BaseModel]:
        return APICallToolOutputs

    @classmethod
    def get_canonical_ports(cls) -> dict[str, str | None]:
        return {"input": "request_body", "output": "output"}

    def __init__(
        self,
        trace_manager: TraceManager,
        component_attributes: ComponentAttributes,
        endpoint: str,
        method: str = "GET",
        headers: Optional[Union[Dict[str, Any], str]] = None,
        timeout: int = 30,
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
        inputs: APICallToolInputs,
        ctx: Optional[dict] = None,
    ) -> APICallToolOutputs:
        dynamic_params = {}
        request_data = inputs.request_body

        if isinstance(request_data, str):
            try:
                request_data = json.loads(request_data)
            except json.JSONDecodeError:
                pass

        if isinstance(request_data, dict):
            dynamic_params.update(request_data)
        elif request_data is not None:
            dynamic_params["body"] = request_data

        if inputs.model_extra:
            dynamic_params.update(inputs.model_extra)

        api_response = await self.make_api_call(**dynamic_params)

        # Format the API response as a readable message
        if api_response.get("success", False):
            content = json.dumps(api_response["data"], indent=2)
        else:
            content = f"API call failed: {api_response.get('error', 'Unknown error')}"

        return APICallToolOutputs(
            output=content,
            artifacts={"api_response": api_response},
        )
