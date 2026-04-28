from typing import Optional, Type

from openinference.semconv.trace import OpenInferenceSpanKindValues
from pydantic import BaseModel, Field

from engine.components.component import Component
from engine.components.types import ComponentAttributes, ToolDescription
from engine.integrations.gmail.gmail_sender import GmailSenderInputs
from engine.integrations.gmail.gmail_sender_v2 import GmailSenderV2
from engine.integrations.outlook.outlook_sender import OutlookSender, OutlookSenderInputs
from engine.trace.trace_manager import TraceManager

MAIL_SENDER_TOOL_DESCRIPTION = ToolDescription(
    name="Mail Sender",
    description=(
        "Send email using Gmail or Microsoft Outlook. "
        "Connect exactly one provider (Gmail or Outlook) in the component settings."
    ),
    tool_properties={
        "from_email": {
            "type": "string",
            "description": (
                "Optional sender alias (Gmail only). Must be a verified 'Send mail as' alias "
                "on the connected account. Ignored when using Outlook."
            ),
        },
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
            "description": "List of CC email addresses.",
        },
        "bcc": {
            "type": "array",
            "items": {"type": "string"},
            "description": "List of BCC email addresses.",
        },
        "email_attachments": {
            "type": "array",
            "items": {"type": "string"},
            "description": "List of file paths to attach to the email.",
        },
    },
    required_tool_properties=["mail_subject"],
)


class MailSenderOutputs(BaseModel):
    status: str = Field(description="The status of the email operation.")
    message_id: Optional[str] = Field(
        default=None,
        description="The provider message or draft ID when available.",
    )


class MailSender(Component):
    """Unified mail sender: delegates to Gmail or Outlook based on OAuth configuration."""

    TRACE_SPAN_KIND = OpenInferenceSpanKindValues.TOOL.value
    migrated = True

    def __init__(
        self,
        trace_manager: TraceManager,
        component_attributes: ComponentAttributes,
        gmail_access_token: Optional[str] = None,
        outlook_access_token: Optional[str] = None,
        save_as_draft: bool = True,
        tool_description: ToolDescription = MAIL_SENDER_TOOL_DESCRIPTION,
    ):
        super().__init__(
            trace_manager,
            tool_description=tool_description,
            component_attributes=component_attributes,
        )
        self._gmail_access_token = gmail_access_token
        self._outlook_access_token = outlook_access_token
        self.save_as_draft = save_as_draft

    @classmethod
    def get_inputs_schema(cls) -> Type[BaseModel]:
        return GmailSenderInputs

    @classmethod
    def get_outputs_schema(cls) -> Type[BaseModel]:
        return MailSenderOutputs

    @classmethod
    def get_canonical_ports(cls) -> dict[str, str | None]:
        return {"input": "mail_body", "output": "status"}

    def is_available(self) -> bool:
        g = bool(self._gmail_access_token)
        o = bool(self._outlook_access_token)
        return g ^ o

    async def _run_without_io_trace(self, inputs: BaseModel, ctx: dict) -> MailSenderOutputs:
        gi = GmailSenderInputs.model_validate(inputs.model_dump())
        g = bool(self._gmail_access_token)
        o = bool(self._outlook_access_token)
        if g and o:
            raise ValueError(
                "Mail Sender allows only one provider: disconnect either Gmail or Outlook "
                "and keep a single connection."
            )
        if not g and not o:
            raise ValueError(
                "Mail Sender requires a Gmail or Outlook connection. "
                "Please connect one provider in the component settings."
            )
        if g:
            gmail_inner = GmailSenderV2(
                trace_manager=self.trace_manager,
                component_attributes=self.component_attributes,
                access_token=self._gmail_access_token,
                save_as_draft=self.save_as_draft,
                tool_description=self.tool_description,
            )
            out = await gmail_inner._run_without_io_trace(gi, ctx)
            return MailSenderOutputs(status=out.status, message_id=out.message_id)
        outlook_inner = OutlookSender(
            trace_manager=self.trace_manager,
            component_attributes=self.component_attributes,
            access_token=self._outlook_access_token,
            save_as_draft=self.save_as_draft,
            tool_description=self.tool_description,
        )
        outlook_inputs = OutlookSenderInputs.model_validate(gi.model_dump())
        out = await outlook_inner._run_without_io_trace(outlook_inputs, ctx)
        return MailSenderOutputs(status=out.status, message_id=out.message_id)
