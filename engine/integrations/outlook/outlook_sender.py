import logging
from pathlib import Path
from typing import Iterable, Optional, Type
from uuid import UUID

import httpx
from openinference.semconv.trace import OpenInferenceSpanKindValues, SpanAttributes
from opentelemetry.trace import get_current_span
from pydantic import BaseModel, Field, field_validator

from engine.components.component import Component
from engine.components.types import ComponentAttributes, ToolDescription
from engine.integrations.outlook.errors import OutlookAPIError
from engine.integrations.outlook.outlook_utils import GRAPH_API_BASE, build_graph_mail_payload
from engine.trace.serializer import serialize_to_json
from engine.trace.trace_manager import TraceManager

LOGGER = logging.getLogger(__name__)

OUTLOOK_GROUP_EMAIL_CONTENT_ID = UUID("a3f1b2c4-d5e6-4f7a-8b9c-0d1e2f3a4b5c")
OUTLOOK_GROUP_RECIPIENTS_ID = UUID("b4c2d3e5-f6a7-4b8c-9d0e-1f2a3b4c5d6e")
OUTLOOK_GROUP_ATTACHMENTS_ID = UUID("c5d3e4f6-a7b8-4c9d-0e1f-2a3b4c5d6e7f")

OUTLOOK_SENDER_TOOL_DESCRIPTION = ToolDescription(
    name="Outlook Sender",
    description="A tool to send emails using Microsoft Outlook via the Graph API.",
    tool_properties={
        "mail_subject": {
            "type": "string",
            "description": "The subject of the email to be sent.",
        },
        "mail_body": {
            "type": "string",
            "description": "The body of the email to be sent.",
        },
        "mail_html_body": {
            "type": "string",
            "description": "Optional HTML body of the email. When provided, used instead of mail_body.",
        },
        "email_recipients": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "List of email addresses to send the email to. "
                "If not provided, the email will be saved as a draft without recipients."
            ),
        },
        "cc": {
            "type": "array",
            "items": {"type": "string"},
            "description": "List of CC email addresses to send the email to.",
        },
        "bcc": {
            "type": "array",
            "items": {"type": "string"},
            "description": "List of BCC email addresses to send the email to.",
        },
        "email_attachments": {
            "type": "array",
            "items": {"type": "string"},
            "description": "List of file paths to attach to the email.",
        },
    },
    required_tool_properties=["mail_subject"],
)


class OutlookSenderInputs(BaseModel):
    mail_subject: str = Field(
        description="The subject of the email to be sent.",
        json_schema_extra={
            "is_tool_input": True,
            "display_order": 1,
            "parameter_group_id": OUTLOOK_GROUP_EMAIL_CONTENT_ID,
            "parameter_order_within_group": 1,
        },
    )
    mail_body: Optional[str] = Field(
        default=None,
        description="The body of the email to be sent.",
        json_schema_extra={
            "is_tool_input": True,
            "display_order": 2,
            "parameter_group_id": OUTLOOK_GROUP_EMAIL_CONTENT_ID,
            "parameter_order_within_group": 2,
        },
    )
    mail_html_body: Optional[str] = Field(
        default=None,
        description="Optional HTML body of the email. When provided, used instead of mail_body.",
        json_schema_extra={
            "is_tool_input": True,
            "display_order": 3,
            "parameter_group_id": OUTLOOK_GROUP_EMAIL_CONTENT_ID,
            "parameter_order_within_group": 3,
        },
    )
    email_recipients: Optional[list[str]] = Field(
        default=None,
        description="List of email addresses to send the email to. "
        "If not provided, the email will be saved as a draft.",
        json_schema_extra={
            "is_tool_input": True,
            "display_order": 4,
            "parameter_group_id": OUTLOOK_GROUP_RECIPIENTS_ID,
            "parameter_order_within_group": 1,
        },
    )
    cc: Optional[list[str]] = Field(
        default=None,
        description="List of CC email addresses to send the email to.",
        json_schema_extra={
            "is_tool_input": True,
            "display_order": 5,
            "parameter_group_id": OUTLOOK_GROUP_RECIPIENTS_ID,
            "parameter_order_within_group": 2,
        },
    )
    bcc: Optional[list[str]] = Field(
        default=None,
        description="List of BCC email addresses to send the email to.",
        json_schema_extra={
            "is_tool_input": True,
            "display_order": 6,
            "parameter_group_id": OUTLOOK_GROUP_RECIPIENTS_ID,
            "parameter_order_within_group": 3,
        },
    )
    email_attachments: Optional[list[str]] = Field(
        default=None,
        description="List of file paths to attach to the email.",
        json_schema_extra={
            "is_tool_input": True,
            "display_order": 7,
            "parameter_group_id": OUTLOOK_GROUP_ATTACHMENTS_ID,
            "parameter_order_within_group": 1,
        },
    )

    @field_validator("email_recipients", mode="before")
    @classmethod
    def validate_email_recipients(cls, v):
        if isinstance(v, str):
            return [v]
        return v


class OutlookSenderOutputs(BaseModel):
    status: str = Field(description="The status of the email operation.")
    message_id: Optional[str] = Field(
        default=None,
        description="The ID of the draft message, or None when the email was submitted for delivery.",
    )


class OutlookSender(Component):
    """Outlook sender using Nango OAuth. Receives access_token directly (injected by OAuthComponentFactory)."""

    TRACE_SPAN_KIND = OpenInferenceSpanKindValues.TOOL.value
    migrated = True

    @classmethod
    def get_inputs_schema(cls) -> Type[BaseModel]:
        return OutlookSenderInputs

    @classmethod
    def get_outputs_schema(cls) -> Type[BaseModel]:
        return OutlookSenderOutputs

    @classmethod
    def get_canonical_ports(cls) -> dict[str, str | None]:
        return {"input": "mail_body", "output": "status"}

    def __init__(
        self,
        trace_manager: TraceManager,
        component_attributes: ComponentAttributes,
        access_token: Optional[str] = None,
        save_as_draft: bool = True,
        tool_description: ToolDescription = OUTLOOK_SENDER_TOOL_DESCRIPTION,
    ):
        super().__init__(
            trace_manager,
            tool_description=tool_description,
            component_attributes=component_attributes,
        )
        self.access_token = access_token
        self._email_address: Optional[str] = None
        self.save_as_draft = save_as_draft

    def is_available(self) -> bool:
        return bool(self.access_token)

    def _auth_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    async def outlook_create_draft(
        self,
        email_subject: str,
        email_body: Optional[str] = None,
        email_recipients: Optional[list[str]] = None,
        cc: Optional[list[str]] = None,
        bcc: Optional[list[str]] = None,
        attachments: Optional[Iterable[str | Path]] = None,
        html_body: Optional[str] = None,
    ) -> dict:
        message_payload = build_graph_mail_payload(
            subject=email_subject,
            body=email_body,
            recipients=email_recipients,
            cc=cc,
            bcc=bcc,
            attachments=attachments,
            html_body=html_body,
        )
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{GRAPH_API_BASE}/me/messages",
                headers=self._auth_headers(),
                json=message_payload,
                timeout=30.0,
            )
        if response.status_code not in (200, 201):
            LOGGER.error("Failed to create Outlook draft: status=%s", response.status_code)
            raise OutlookAPIError("create Outlook draft", response.status_code)
        draft = response.json()
        LOGGER.debug(f"Draft id: {draft['id']}")
        return draft

    async def outlook_send_email(
        self,
        email_subject: str,
        email_body: Optional[str] = None,
        email_recipients: Optional[list[str]] = None,
        cc: Optional[list[str]] = None,
        bcc: Optional[list[str]] = None,
        attachments: Optional[Iterable[str | Path]] = None,
        html_body: Optional[str] = None,
    ) -> None:
        message_payload = build_graph_mail_payload(
            subject=email_subject,
            body=email_body,
            recipients=email_recipients,
            cc=cc,
            bcc=bcc,
            attachments=attachments,
            html_body=html_body,
        )
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{GRAPH_API_BASE}/me/sendMail",
                headers=self._auth_headers(),
                json={"message": message_payload},
                timeout=30.0,
            )
        if response.status_code not in (200, 202):
            LOGGER.error("Failed to send Outlook email: status=%s", response.status_code)
            raise OutlookAPIError("send Outlook email", response.status_code)

    async def _run_without_io_trace(self, inputs: OutlookSenderInputs, ctx: dict) -> OutlookSenderOutputs:
        if not self.access_token:
            raise ValueError(
                "Outlook Sender requires a configured OAuth connection. "
                "Please select an Outlook connection in the component settings."
            )
        if not inputs.mail_subject:
            raise ValueError("Email subject must be provided")
        span = get_current_span()
        span.set_attributes({
            SpanAttributes.INPUT_VALUE: serialize_to_json(
                {
                    "mail_subject": inputs.mail_subject,
                    "mail_body": inputs.mail_body,
                    "email_recipients": inputs.email_recipients,
                    "cc": inputs.cc,
                    "bcc": inputs.bcc,
                    "email_attachments": inputs.email_attachments,
                    "mail_html_body": inputs.mail_html_body,
                    "save_as_draft": self.save_as_draft,
                },
                shorten_string=True,
            ),
        })
        if self.save_as_draft or not inputs.email_recipients:
            LOGGER.info("Creating Outlook draft email")
            draft = await self.outlook_create_draft(
                email_subject=inputs.mail_subject,
                email_body=inputs.mail_body,
                email_recipients=inputs.email_recipients,
                cc=inputs.cc,
                bcc=inputs.bcc,
                attachments=inputs.email_attachments,
                html_body=inputs.mail_html_body,
            )
            status = f"Draft created successfully with ID: {draft['id']}"
            message_id = draft["id"]
        else:
            await self.outlook_send_email(
                email_subject=inputs.mail_subject,
                email_body=inputs.mail_body,
                email_recipients=inputs.email_recipients,
                cc=inputs.cc,
                bcc=inputs.bcc,
                attachments=inputs.email_attachments,
                html_body=inputs.mail_html_body,
            )
            status = "Email sent successfully"
            message_id = None
        span.set_attributes({
            SpanAttributes.OUTPUT_VALUE: serialize_to_json(
                {"status": status, "message_id": message_id},
                shorten_string=True,
            ),
        })
        return OutlookSenderOutputs(status=status, message_id=message_id)
