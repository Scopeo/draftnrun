import json
from typing import Any, Optional, Type

from openinference.semconv.trace import OpenInferenceSpanKindValues
from pydantic import BaseModel, Field

from ada_backend.database.models import ParameterType, UIComponent, UIComponentProperties
from engine.components.tools.api_call_tool import APICallTool
from engine.components.types import ComponentAttributes, ToolDescription
from engine.components.utils import load_str_to_json
from engine.trace.trace_manager import TraceManager

HUBSPOT_OWNER_ENDPOINT = "https://api.hubapi.com/crm/v3/owners/{owner_id}"

HUBSPOT_OWNER_TOOL_DESCRIPTION = ToolDescription(
    name="hubspot_owner",
    description="Get a HubSpot owner by owner ID.",
    tool_properties={
        "owner_id": {
            "type": "string",
            "description": "The HubSpot owner ID to retrieve.",
        },
    },
    required_tool_properties=["owner_id"],
)


class HubSpotOwnerInputs(BaseModel):
    headers: Optional[dict[str, str] | str] = Field(
        default_factory=dict,
        description="The headers to send to HubSpot, including Authorization.",
        json_schema_extra={
            "parameter_type": ParameterType.JSON,
            "is_tool_input": False,
            "ui_component": UIComponent.JSON_TEXTAREA,
            "ui_component_properties": UIComponentProperties(
                label="Headers",
                placeholder='{"Authorization": "Bearer hubspot_token"}',
            ).model_dump(exclude_unset=True, exclude_none=True),
        },
    )
    owner_id: str = Field(
        description="The HubSpot owner ID to retrieve.",
        json_schema_extra={
            "ui_component": UIComponent.TEXTFIELD,
            "ui_component_properties": UIComponentProperties(
                label="Owner ID",
                placeholder="1361098942",
                description="The HubSpot owner ID, for example a contact's hubspot_owner_id.",
            ).model_dump(exclude_unset=True, exclude_none=True),
        },
    )

class HubSpotOwnerOutputs(BaseModel):
    output: str = Field(description="The raw owner response formatted as JSON.")
    status_code: int = Field(description="The status code of the HubSpot owner API response.")
    success: bool = Field(description="Whether the HubSpot owner lookup succeeded.")
    id: Optional[str] = Field(default=None, description="The HubSpot owner ID.")
    email: Optional[str] = Field(default=None, description="The owner's email address.")
    type: Optional[str] = Field(default=None, description="The HubSpot owner type.")
    firstName: Optional[str] = Field(default=None, description="The owner's first name.")
    lastName: Optional[str] = Field(default=None, description="The owner's last name.")
    userId: Optional[int] = Field(default=None, description="The active HubSpot user ID.")
    userIdIncludingInactive: Optional[int] = Field(
        default=None,
        description="The HubSpot user ID, including inactive users.",
    )
    createdAt: Optional[str] = Field(default=None, description="When the owner was created.")
    updatedAt: Optional[str] = Field(default=None, description="When the owner was last updated.")
    archived: Optional[bool] = Field(default=None, description="Whether the owner is archived.")


class HubSpotOwnerTool(APICallTool):
    TRACE_SPAN_KIND = OpenInferenceSpanKindValues.TOOL.value
    migrated = True

    @classmethod
    def get_inputs_schema(cls) -> Type[BaseModel]:
        return HubSpotOwnerInputs

    @classmethod
    def get_outputs_schema(cls) -> Type[BaseModel]:
        return HubSpotOwnerOutputs

    @classmethod
    def get_canonical_ports(cls) -> dict[str, str | None]:
        return {"input": "owner_id", "output": "output"}

    def __init__(
        self,
        trace_manager: TraceManager,
        component_attributes: ComponentAttributes,
        method: str = "GET",
        timeout: int = 30,
        tool_description: ToolDescription = HUBSPOT_OWNER_TOOL_DESCRIPTION,
    ) -> None:
        super().__init__(
            trace_manager=trace_manager,
            tool_description=tool_description,
            component_attributes=component_attributes,
            method=method,
            timeout=timeout,
        )

    async def _run_without_io_trace(
        self,
        inputs: HubSpotOwnerInputs,
        ctx: Optional[dict] = None,
    ) -> HubSpotOwnerOutputs:
        headers = load_str_to_json(inputs.headers) if isinstance(inputs.headers, str) else inputs.headers or {}
        endpoint = HUBSPOT_OWNER_ENDPOINT.format(owner_id=inputs.owner_id)
        api_response = await self.make_api_call(
            headers=headers,
            fixed_parameters={},
            endpoint=endpoint,
        )
        if api_response.get("success", False):
            data: dict[str, Any] = api_response.get("data", {})
            output = json.dumps(data, indent=2)
        else:
            data = {}
            output = f"HubSpot owner lookup failed: {api_response.get('error', 'Unknown error')}"
        return HubSpotOwnerOutputs(
            output=output,
            status_code=api_response["status_code"],
            success=api_response["success"],
            **data,
        )
