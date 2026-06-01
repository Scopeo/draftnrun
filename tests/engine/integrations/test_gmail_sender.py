import base64
from email import message_from_bytes
from unittest.mock import MagicMock, patch

import pytest

from engine.components.types import ComponentAttributes
from engine.integrations.gmail.gmail_sender import GmailSenderInputs
from engine.integrations.gmail.gmail_sender_v2 import GmailNeverdropSender
from engine.integrations.gmail.gmail_utils import create_raw_mail_message
from engine.integrations.utils import normalize_str_list


class TestNormalizeStrList:
    def test_single_string_wrapped_in_list(self):
        assert normalize_str_list("file.pdf") == ["file.pdf"]

    def test_list_of_strings_passes_through(self):
        assert normalize_str_list(["a.pdf", "b.docx"]) == ["a.pdf", "b.docx"]

    def test_nested_list_is_flattened(self):
        assert normalize_str_list([["a.pdf", "b.docx"]]) == ["a.pdf", "b.docx"]

    def test_none_passes_through(self):
        assert normalize_str_list(None) is None

    def test_empty_list_passes_through(self):
        assert normalize_str_list([]) == []


class TestGmailSenderInputsValidation:
    """Regression: email_attachments uses normalize_str_list via field_validator."""

    def test_single_string_wrapped_in_list(self):
        inputs = GmailSenderInputs(mail_subject="test", email_attachments="file.pdf")
        assert inputs.email_attachments == ["file.pdf"]

    def test_nested_list_is_flattened(self):
        inputs = GmailSenderInputs(mail_subject="test", email_attachments=[["a.pdf", "b.docx"]])
        assert inputs.email_attachments == ["a.pdf", "b.docx"]

    def test_none_stays_none(self):
        inputs = GmailSenderInputs(mail_subject="test", email_attachments=None)
        assert inputs.email_attachments is None


class TestFromEmailField:
    def test_defaults_to_none(self):
        inputs = GmailSenderInputs(mail_subject="test")
        assert inputs.from_email is None

    def test_accepts_alias_email(self):
        inputs = GmailSenderInputs(mail_subject="test", from_email="alias@example.com")
        assert inputs.from_email == "alias@example.com"


class TestCreateRawMailMessageFromHeader:
    def _decode_from(self, raw: dict) -> str:
        msg_bytes = base64.urlsafe_b64decode(raw["raw"])
        return message_from_bytes(msg_bytes)["From"]

    @patch("engine.integrations.gmail.gmail_utils._ensure_paths", return_value=[])
    def test_from_header_uses_sender_email_address(self, _mock):
        raw = create_raw_mail_message(subject="hi", sender_email_address="primary@example.com", body="body")
        assert self._decode_from(raw) == "primary@example.com"

    @patch("engine.integrations.gmail.gmail_utils._ensure_paths", return_value=[])
    def test_from_header_uses_alias_when_provided(self, _mock):
        raw = create_raw_mail_message(subject="hi", sender_email_address="alias@example.com", body="body")
        assert self._decode_from(raw) == "alias@example.com"


class TestGmailNeverdropSender:
    @pytest.mark.asyncio
    async def test_sends_email_even_when_draft_requested(self):
        sender = GmailNeverdropSender(
            trace_manager=MagicMock(),
            component_attributes=ComponentAttributes(component_instance_name="gmail_neverdrop"),
            save_as_draft=True,
        )
        sender.gmail_send_email = MagicMock(return_value={"id": "sent-1"})
        sender.gmail_create_draft = MagicMock()

        out = await sender._run_without_io_trace(
            GmailNeverdropSender.get_inputs_schema()(
                mail_subject="subject",
                mail_body="body",
                email_recipients=["to@example.com"],
            ),
            {},
        )

        assert out.message_id == "sent-1"
        assert out.status == "Email sent successfully with ID: sent-1"
        sender.gmail_send_email.assert_called_once()
        sender.gmail_create_draft.assert_not_called()

    @pytest.mark.asyncio
    async def test_rejects_missing_recipients_instead_of_creating_draft(self):
        sender = GmailNeverdropSender(
            trace_manager=MagicMock(),
            component_attributes=ComponentAttributes(component_instance_name="gmail_neverdrop"),
        )
        sender.gmail_create_draft = MagicMock()

        with pytest.raises(ValueError, match="drafts are not supported"):
            await sender._run_without_io_trace(
                GmailNeverdropSender.get_inputs_schema()(
                    mail_subject="subject",
                    mail_body="body",
                    email_recipients=[],
                ),
                {},
            )

        sender.gmail_create_draft.assert_not_called()
