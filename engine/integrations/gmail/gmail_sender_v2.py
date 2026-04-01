import logging
from pathlib import Path
from typing import Iterable, Optional, Type

from googleapiclient.errors import HttpError
from openinference.semconv.trace import OpenInferenceSpanKindValues, SpanAttributes
from opentelemetry.trace import get_current_span
from pydantic import BaseModel

from engine.components.component import Component
from engine.components.types import ComponentAttributes, ToolDescription
from engine.integrations.gmail.gmail_sender import (
    GMAIL_SENDER_TOOL_DESCRIPTION,
    GmailSenderInputs,
    GmailSenderOutputs,
)
from engine.integrations.gmail.gmail_utils import create_raw_mail_message
from engine.integrations.utils import get_gmail_sender_service, get_google_user_email
from engine.trace.serializer import serialize_to_json
from engine.trace.trace_manager import TraceManager

LOGGER = logging.getLogger(__name__)


class GmailSenderV2(Component):
    """Gmail sender using Nango OAuth. Receives access_token directly (injected by OAuthComponentFactory)."""

    TRACE_SPAN_KIND = OpenInferenceSpanKindValues.TOOL.value
    migrated = True

    @classmethod
    def get_inputs_schema(cls) -> Type[BaseModel]:
        return GmailSenderInputs

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
        access_token: Optional[str] = None,
        save_as_draft: bool = True,
        tool_description: ToolDescription = GMAIL_SENDER_TOOL_DESCRIPTION,
    ):
        super().__init__(
            trace_manager,
            tool_description=tool_description,
            component_attributes=component_attributes,
        )
        self._access_token = access_token
        self._service = None
        self._email_address = None
        self.save_as_draft = save_as_draft

    def is_available(self) -> bool:
        return bool(self._access_token)

    def _ensure_client(self) -> None:
        if not self._access_token:
            raise ValueError(
                "Gmail Sender requires a configured OAuth connection. "
                "Please select a Gmail connection in the component settings."
            )
        if self._service is None:
            self._service = get_gmail_sender_service(self._access_token)
            self._email_address = get_google_user_email(self._access_token)

    @property
    def service(self):
        self._ensure_client()
        return self._service

    @property
    def email_address(self) -> str:
        self._ensure_client()
        return self._email_address

    def gmail_create_draft(
        self,
        email_subject: str,
        email_body: Optional[str] = None,
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
                sender_email_address=self.email_address,
                recipients=email_recipients,
                cc=cc,
                bcc=bcc,
                attachments=attachments,
                html_body=html_body,
            )
            draft = self.service.users().drafts().create(userId="me", body={"message": raw_email_message}).execute()
            LOGGER.debug(f"Draft id: {draft['id']}\nDraft message: {draft['message']}")

        except HttpError as error:
            LOGGER.error(f"An error occurred: {error}")
            draft = None
        return draft

    def gmail_send_email(
        self,
        email_subject: str,
        email_body: Optional[str] = None,
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
                sender_email_address=self.email_address,
                recipients=email_recipients,
                cc=cc,
                bcc=bcc,
                attachments=attachments,
                html_body=html_body,
            )
            sent_message = self.service.users().messages().send(userId="me", body=create_message).execute()
            LOGGER.debug(f"Message sent successfully: {sent_message}")
        except HttpError as error:
            LOGGER.error(f"An error occurred while sending the email: {error}")
            raise RuntimeError(f"Failed to send email: {error}")
        return sent_message

    async def _run_without_io_trace(self, inputs: GmailSenderInputs, ctx: dict) -> GmailSenderOutputs:
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
                },
                shorten_string=True,
            ),
        })
        if self.save_as_draft or not inputs.email_recipients:
            LOGGER.info("Creating draft email")
            draft = self.gmail_create_draft(
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
            sent_message = self.gmail_send_email(
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
