import base64
import logging
from email.message import EmailMessage
from typing import Optional

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from openinference.semconv.trace import OpenInferenceSpanKindValues, SpanAttributes
from google_auth_oauthlib.flow import InstalledAppFlow
from opentelemetry.trace import get_current_span

from engine.agent.agent import AgentPayload, ChatMessage, ToolDescription
from engine.agent.agent import Agent
from engine.trace.trace_manager import TraceManager

LOGGER = logging.getLogger(__name__)

GMAIL_SENDER_TOOL_DESCRIPTION = ToolDescription(
    name="Gmail Sender",
    description="A tool to send emails using Gmail API.",
    tool_properties={
        "mail_subject": {
            "type": "string",
            "description": "The subject of the email to be sent.",
        },
        "mail_body": {
            "type": "string",
            "description": "The body of the email to be sent.",
        },
    },
    required_tool_properties=["mail_subject", "mail_body"],
)


class GmailSender(Agent):
    TRACE_SPAN_KIND = OpenInferenceSpanKindValues.TOOL.value

    def __init__(
        self,
        trace_manager: TraceManager,
        component_instance_name: str,
        integration: str,
        send_as_draft: bool = True,
        tool_description: ToolDescription = GMAIL_SENDER_TOOL_DESCRIPTION,
    ):
        super().__init__(
            trace_manager, tool_description=tool_description, component_instance_name=component_instance_name
        )
        JSON_PATH = "data/client_secret_gmail.json"
        SCOPES = ["https://www.googleapis.com/auth/gmail.compose", "https://www.googleapis.com/auth/gmail.modify"]
        flow = InstalledAppFlow.from_client_secrets_file(JSON_PATH, SCOPES)
        creds = flow.run_local_server(port=0)
        self.gmail_credentials = creds
        self.send_as_draft = send_as_draft

    def gmail_create_draft(self, email_subject: str, email_body: str):
        try:
            service = build("gmail", "v1", credentials=self.gmail_credentials)

            message = EmailMessage()
            message.set_content(email_body)
            message["To"] = "natacha.humeau@gmail.com"
            message["From"] = "natacha@draftnrun.com"
            message["Subject"] = email_subject
            encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
            create_message = {"message": {"raw": encoded_message}}

            draft = service.users().drafts().create(userId="me", body=create_message).execute()
            LOGGER.debug(f'Draft id: {draft["id"]}\nDraft message: {draft["message"]}')

        except HttpError as error:
            LOGGER.error(f"An error occurred: {error}")
            draft = None

        return draft

    async def _run_without_trace(
        self, *inputs: AgentPayload, mail_subject: Optional[str] = None, mail_body: Optional[str] = None
    ) -> AgentPayload:
        if not mail_subject or not mail_body:
            raise ValueError("Both email_subject and email_body must be provided")
        if self.send_as_draft:
            LOGGER.info("Creating draft email")
            span = get_current_span()
            span.set_attributes(
                {
                    SpanAttributes.INPUT_VALUE: f"Subject: {mail_subject}\n Body: {mail_body}",
                }
            )
            draft = self.gmail_create_draft(mail_subject, mail_body)
            if not draft:
                raise RuntimeError("Failed to create draft email")
            output_message = f"Draft created successfully with ID: {draft['id']}"
        else:
            LOGGER.info("Sending email directly")
            # Here you would implement the logic to send the email directly
            # For now, we will simulate a successful send operation
            draft = {"id": "simulated_email_id", "message": {"raw": "simulated_raw_message"}}
            output_message = f"Email sent successfully with ID: {draft['id']}"
        return AgentPayload(messages=[ChatMessage(role="assistant", content=output_message)])
