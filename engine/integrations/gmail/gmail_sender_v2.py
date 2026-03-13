import logging
from pathlib import Path
from typing import Iterable, Optional, Type

from googleapiclient.errors import HttpError
from openinference.semconv.trace import OpenInferenceSpanKindValues, SpanAttributes
from opentelemetry.trace import get_current_span
from pydantic import BaseModel, Field

from ada_backend.database.models import UIComponent, UIComponentProperties
from ada_backend.services.integration_service import resolve_oauth_access_token
from engine.components.component import Component
from engine.components.types import ComponentAttributes, ToolDescription
from engine.integrations.gmail.gmail_sender import (
    GMAIL_SENDER_TOOL_DESCRIPTION,
    GmailSenderInputs,
    GmailSenderOutputs,
)
from engine.integrations.gmail.gmail_utils import create_raw_mail_message
from engine.integrations.providers import OAuthProvider
from engine.integrations.utils import get_gmail_sender_service, get_google_user_email
from engine.trace.serializer import serialize_to_json
from engine.trace.trace_manager import TraceManager

LOGGER = logging.getLogger(__name__)


class GmailSenderV2Inputs(GmailSenderInputs):
    oauth_connection_id: str = Field(
        description="OAuth connection for Gmail",
        json_schema_extra={
            "is_tool_input": False,
            "ui_component": UIComponent.OAUTH_CONNECTION,
            "ui_component_properties": UIComponentProperties(
                label="Gmail Connection",
                description="Select your authorized Gmail account connection",
                provider=OAuthProvider.GMAIL.value,
                icon="logos-google-gmail",
            ).model_dump(exclude_unset=True, exclude_none=True),
        },
    )


class GmailSenderV2(Component):
    """Gmail sender using Nango OAuth. Resolves access_token at runtime from oauth_connection_id."""

    TRACE_SPAN_KIND = OpenInferenceSpanKindValues.TOOL.value
    migrated = True

    @classmethod
    def get_inputs_schema(cls) -> Type[BaseModel]:
        return GmailSenderV2Inputs

    @classmethod
    def get_outputs_schema(cls) -> Type[BaseModel]:
        return GmailSenderOutputs

    @classmethod
    def get_canonical_ports(cls) -> dict[str, str | None]:
        return {"input": "mail_body", "output": "status"}

    def __init__(
        self,
        trace_manager: TraceManager,
        component_attributes: ComponentAttributes,
        save_as_draft: bool = True,
        tool_description: ToolDescription = GMAIL_SENDER_TOOL_DESCRIPTION,
    ):
        super().__init__(
            trace_manager,
            tool_description=tool_description,
            component_attributes=component_attributes,
        )
        self.save_as_draft = save_as_draft

    def _gmail_create_draft(
        self,
        service,
        email_address: str,
        email_subject: str,
        email_body: str,
        email_recipients: Optional[list[str]] = None,
        cc: Optional[list[str]] = None,
        bcc: Optional[list[str]] = None,
        attachments: Optional[Iterable[str | Path]] = None,
        html_body: Optional[str] = None,
    ):
        try:
            raw_email_message = create_raw_mail_message(
                subject=email_subject,
                body=email_body,
                sender_email_address=email_address,
                recipients=email_recipients,
                cc=cc,
                bcc=bcc,
                attachments=attachments,
                html_body=html_body,
            )
            draft = service.users().drafts().create(userId="me", body={"message": raw_email_message}).execute()
            LOGGER.debug(f"Draft id: {draft['id']}\nDraft message: {draft['message']}")

        except HttpError as error:
            LOGGER.error(f"An error occurred: {error}")
            draft = None
        return draft

    def _gmail_send_email(
        self,
        service,
        email_address: str,
        email_subject: str,
        email_body: str,
        email_recipients: Optional[list[str]] = None,
        cc: Optional[list[str]] = None,
        bcc: Optional[list[str]] = None,
        attachments: Optional[Iterable[str | Path]] = None,
        html_body: Optional[str] = None,
    ):
        try:
            create_message = create_raw_mail_message(
                subject=email_subject,
                body=email_body,
                sender_email_address=email_address,
                recipients=email_recipients,
                cc=cc,
                bcc=bcc,
                attachments=attachments,
                html_body=html_body,
            )
            sent_message = service.users().messages().send(userId="me", body=create_message).execute()
            LOGGER.debug(f"Message sent successfully: {sent_message}")
        except HttpError as error:
            LOGGER.error(f"An error occurred while sending the email: {error}")
            raise RuntimeError(f"Failed to send email: {error}")
        return sent_message

    async def _run_without_io_trace(self, inputs: GmailSenderV2Inputs, ctx: dict) -> GmailSenderOutputs:
        if not inputs.mail_subject or not inputs.mail_body:
            raise ValueError("Both email_subject and email_body must be provided")

        access_token = await resolve_oauth_access_token(
            definition_id=inputs.oauth_connection_id,
            provider_config_key=OAuthProvider.GMAIL.value,
        )
        service = get_gmail_sender_service(access_token)
        email_address = get_google_user_email(access_token)

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
                },
                shorten_string=True,
            ),
        })
        if self.save_as_draft or not inputs.email_recipients:
            LOGGER.info("Creating draft email")
            draft = self._gmail_create_draft(
                service=service,
                email_address=email_address,
                email_subject=inputs.mail_subject,
                email_body=inputs.mail_body,
                email_recipients=inputs.email_recipients,
                cc=inputs.cc,
                bcc=inputs.bcc,
                attachments=inputs.email_attachments,
                html_body=inputs.mail_html_body,
            )
            if not draft:
                raise RuntimeError("Failed to create draft email")
            status = f"Draft created successfully with ID: {draft['id']}"
            message_id = draft["id"]
        else:
            sent_message = self._gmail_send_email(
                service=service,
                email_address=email_address,
                email_subject=inputs.mail_subject,
                email_body=inputs.mail_body,
                email_recipients=inputs.email_recipients,
                cc=inputs.cc,
                bcc=inputs.bcc,
                attachments=inputs.email_attachments,
                html_body=inputs.mail_html_body,
            )
            status = f"Email sent successfully with ID: {sent_message['id']}"
            message_id = sent_message["id"]
        return GmailSenderOutputs(status=status, message_id=message_id)
