import logging
from pathlib import Path
from typing import Iterable, Optional, Type

import httpx
from openinference.semconv.trace import OpenInferenceSpanKindValues, SpanAttributes
from opentelemetry.trace import get_current_span
from pydantic import BaseModel, Field, validator

from engine.components.component import Component
from engine.components.types import ComponentAttributes, ToolDescription
from engine.integrations.outlook.errors import OutlookAPIError
from engine.integrations.outlook.outlook_utils import GRAPH_API_BASE, build_graph_mail_payload, get_outlook_user_email
from engine.trace.serializer import serialize_to_json
from engine.trace.trace_manager import TraceManager

LOGGER = logging.getLogger(__name__)

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
    required_tool_properties=["mail_subject", "mail_body"],
)


class OutlookSenderInputs(BaseModel):
    mail_subject: str = Field(
        description="The subject of the email to be sent.", json_schema_extra={"is_tool_input": True}
    )
    mail_body: str = Field(description="The body of the email to be sent.", json_schema_extra={"is_tool_input": True})
    email_recipients: Optional[list[str]] = Field(
        default=None,
        description="""List of email addresses to send the email to.
            If not provided, the email will be saved as a draft.""",
        json_schema_extra={"is_tool_input": True},
    )
    cc: Optional[list[str]] = Field(
        default=None,
        description="List of CC email addresses to send the email to.",
        json_schema_extra={"is_tool_input": True},
    )
    bcc: Optional[list[str]] = Field(
        default=None,
        description="List of BCC email addresses to send the email to.",
        json_schema_extra={"is_tool_input": True},
    )
    email_attachments: Optional[list[str]] = Field(
        default=None,
        description="List of file paths to attach to the email.",
        json_schema_extra={"is_tool_input": True},
    )

    @validator("email_recipients", pre=True)
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
        access_token: str,
        save_as_draft: bool = True,
        tool_description: ToolDescription = OUTLOOK_SENDER_TOOL_DESCRIPTION,
    ):
        super().__init__(
            trace_manager,
            tool_description=tool_description,
            component_attributes=component_attributes,
        )
        self.access_token = access_token
        self.email_address = get_outlook_user_email(access_token)
        self.save_as_draft = save_as_draft

    def _auth_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    def outlook_create_draft(
        self,
        email_subject: str,
        email_body: str,
        email_recipients: Optional[list[str]] = None,
        cc: Optional[list[str]] = None,
        bcc: Optional[list[str]] = None,
        attachments: Optional[Iterable[str | Path]] = None,
    ) -> dict:
        message_payload = build_graph_mail_payload(
            subject=email_subject,
            body=email_body,
            sender=self.email_address,
            recipients=email_recipients,
            cc=cc,
            bcc=bcc,
            attachments=attachments,
        )
        response = httpx.post(
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

    def outlook_send_email(
        self,
        email_subject: str,
        email_body: str,
        email_recipients: Optional[list[str]] = None,
        cc: Optional[list[str]] = None,
        bcc: Optional[list[str]] = None,
        attachments: Optional[Iterable[str | Path]] = None,
    ) -> None:
        message_payload = build_graph_mail_payload(
            subject=email_subject,
            body=email_body,
            sender=self.email_address,
            recipients=email_recipients,
            cc=cc,
            bcc=bcc,
            attachments=attachments,
        )
        response = httpx.post(
            f"{GRAPH_API_BASE}/me/sendMail",
            headers=self._auth_headers(),
            json={"message": message_payload},
            timeout=30.0,
        )
        if response.status_code not in (200, 202):
            LOGGER.error("Failed to send Outlook email: status=%s", response.status_code)
            raise OutlookAPIError("send Outlook email", response.status_code)

    async def _run_without_io_trace(self, inputs: OutlookSenderInputs, ctx: dict) -> OutlookSenderOutputs:
        if not inputs.mail_subject or not inputs.mail_body:
            raise ValueError("Both email_subject and email_body must be provided")
        span = get_current_span()
        span.set_attributes({
            SpanAttributes.INPUT_VALUE: serialize_to_json(
                {
                    "recipient_count": len(inputs.email_recipients or []),
                    "cc_count": len(inputs.cc or []),
                    "bcc_count": len(inputs.bcc or []),
                    "attachment_count": len(inputs.email_attachments or []),
                },
                shorten_string=True,
            ),
        })
        if self.save_as_draft or not inputs.email_recipients:
            LOGGER.info("Creating Outlook draft email")
            draft = self.outlook_create_draft(
                email_subject=inputs.mail_subject,
                email_body=inputs.mail_body,
                email_recipients=inputs.email_recipients,
                cc=inputs.cc,
                bcc=inputs.bcc,
                attachments=inputs.email_attachments,
            )
            status = f"Draft created successfully with ID: {draft['id']}"
            message_id = draft["id"]
        else:
            self.outlook_send_email(
                email_subject=inputs.mail_subject,
                email_body=inputs.mail_body,
                email_recipients=inputs.email_recipients,
                cc=inputs.cc,
                bcc=inputs.bcc,
                attachments=inputs.email_attachments,
            )
            status = "Email accepted for delivery"
            message_id = None
        return OutlookSenderOutputs(status=status, message_id=message_id)
