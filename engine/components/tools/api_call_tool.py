import json
import logging
import string
from typing import Any, Dict, Optional, Type

import httpx
from openinference.semconv.trace import OpenInferenceSpanKindValues
from pydantic import BaseModel, Field

from ada_backend.database.models import ParameterType, UIComponent, UIComponentProperties
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
    endpoint: str = Field(
        description="The URL of the API endpoint to call.",
        json_schema_extra={
            "is_tool_input": False,
            "ui_component": UIComponent.TEXTFIELD,
            "ui_component_properties": UIComponentProperties(
                label="API Endpoint",
                placeholder="https://api.example.com/endpoint",
                description="The API endpoint URL to send requests to.",
            ).model_dump(exclude_unset=True, exclude_none=True),
        },
    )
    headers: Optional[dict[str, str] | str] = Field(
        default_factory=dict,
        description="The headers to send with the request.",
        json_schema_extra={
            "parameter_type": ParameterType.JSON,
            "is_tool_input": False,
            "ui_component": UIComponent.JSON_TEXTAREA,
            "ui_component_properties": UIComponentProperties(
                label="Headers",
                placeholder='{"Content-Type": "application/json"}',
            ).model_dump(exclude_unset=True, exclude_none=True),
        },
    )
    fixed_parameters: Optional[dict[str, Any] | str] = Field(
        default_factory=dict,
        description="The parameters to send with the request.",
        json_schema_extra={
            "parameter_type": ParameterType.JSON,
            "is_tool_input": False,
            "ui_component": UIComponent.JSON_TEXTAREA,
            "ui_component_properties": UIComponentProperties(
                label="Parameters",
                placeholder='{"api_version": "v2", "format": "json"}',
            ).model_dump(exclude_unset=True, exclude_none=True),
        },
    )
    model_config = {"extra": "allow"}


class APICallToolOutputs(BaseModel):
    output: str = Field(description="The output message to be returned to the user.")
    status_code: int = Field(description="The status code of the API response.")
    data: dict[str, Any] = Field(description="The data of the API response.")
    success: bool = Field(description="Whether the API call was successful.")


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
        return {"input": "endpoint", "output": "output"}

    def __init__(
        self,
        trace_manager: TraceManager,
        component_attributes: ComponentAttributes,
        method: str = "GET",
        timeout: int = 30,
        tool_description: ToolDescription = API_CALL_TOOL_DESCRIPTION,
    ) -> None:
        super().__init__(
            trace_manager=trace_manager,
            tool_description=tool_description,
            component_attributes=component_attributes,
        )
        self.trace_manager = trace_manager
        self.method = method.upper()
        self.timeout = timeout

    async def make_api_call(
        self, headers: dict[str, str], fixed_parameters: dict[str, Any], endpoint: str, **kwargs: Any
    ) -> Dict[str, Any]:
        """Make an HTTP request to the configured API endpoint."""

        request_headers = headers.copy()

        endpoint = endpoint.strip()

        all_parameters = fixed_parameters.copy()
        all_parameters.update(kwargs)
        endpoint = endpoint.format(**all_parameters)
        formatter = string.Formatter()
        used_keys = {field_name for _, field_name, _, _ in formatter.parse(endpoint) if field_name}
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
            status_code = getattr(e.response, "status_code", None) if hasattr(e, "response") else None
            response_body = None
            if hasattr(e, "response") and e.response is not None:
                try:
                    response_body = e.response.json()
                except Exception:
                    response_body = e.response.text
            # TODO(security): `response_body` may echo request headers (e.g. Authorization)
            # returned by misbehaving upstream APIs. Deep redaction of third-party payloads
            # requires a broader policy.
            LOGGER.error(
                "API request failed: %s | status=%s | response_body_type=%s",
                type(e).__name__,
                status_code,
                type(response_body).__name__,
            )
            return {
                "status_code": status_code or 0,
                "error": str(e),
                "response_body": response_body,
                "success": False,
            }

    async def _run_without_io_trace(
        self,
        inputs: APICallToolInputs,
        ctx: Optional[dict] = None,
    ) -> APICallToolOutputs:
        if inputs.headers is not None and isinstance(inputs.headers, str):
            headers = load_str_to_json(inputs.headers)
        else:
            headers = inputs.headers or {}
        if inputs.fixed_parameters is not None and isinstance(inputs.fixed_parameters, str):
            fixed_parameters = load_str_to_json(inputs.fixed_parameters)
        else:
            fixed_parameters = inputs.fixed_parameters or {}
        # Make the API call
        api_response = await self.make_api_call(
            headers=headers,
            fixed_parameters=fixed_parameters,
            endpoint=inputs.endpoint,
            **(inputs.model_extra or {}),
        )

        # Format the API response as a readable message
        if api_response.get("success", False):
            content = json.dumps(api_response["data"], indent=2)
            data = api_response.get("data", {})
        else:
            error_details = {
                "error": api_response.get("error", "Unknown error"),
                "status_code": api_response.get("status_code"),
                "response_body": api_response.get("response_body"),
            }
            content = f"API call failed: {json.dumps(error_details, indent=2)}"
            response_body = api_response.get("response_body")
            if isinstance(response_body, dict):
                data = response_body
            elif response_body is not None:
                data = {"raw": response_body}
            else:
                data = {}

        return APICallToolOutputs(
            output=content,
            status_code=api_response["status_code"],
            data=data,
            success=api_response["success"],
        )
