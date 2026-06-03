import base64
from email import message_from_bytes
from unittest.mock import MagicMock, patch

import pytest

from engine.components.types import ComponentAttributes
from engine.integrations.gmail.gmail_sender import GMAIL_NEVERDROP_SENDER_TOOL_DESCRIPTION, GmailSenderInputs
from engine.integrations.gmail.gmail_sender_v2 import GmailNeverdropSender
from engine.integrations.gmail.gmail_utils import create_raw_mail_message
from engine.integrations.utils import EmailAttachment, normalize_email_attachments, normalize_str_list


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


class TestNormalizeEmailAttachments:
    def test_list_of_strings_passes_through(self):
        assert normalize_email_attachments(["file.pdf"]) == ["file.pdf"]

    def test_none_passes_through(self):
        assert normalize_email_attachments(None) is None

    def test_dict_attachment_is_preserved(self):
        attachments = normalize_email_attachments([{"url": "https://example.com/report", "filename": "report.pdf"}])

        assert attachments == [EmailAttachment(url="https://example.com/report", filename="report.pdf")]

    def test_dict_attachment_requires_url_and_filename(self):
        with pytest.raises(ValueError, match="url"):
            normalize_email_attachments([{"url": "https://example.com/report"}])


class TestGmailSenderInputsValidation:
    """Regression: email_attachments uses normalize_email_attachments via field_validator."""

    def test_list_of_strings_passes_through(self):
        inputs = GmailSenderInputs(mail_subject="test", email_attachments=["file.pdf"])
        assert inputs.email_attachments == ["file.pdf"]

    def test_none_stays_none(self):
        inputs = GmailSenderInputs(mail_subject="test", email_attachments=None)
        assert inputs.email_attachments is None

    def test_dict_attachment_is_accepted(self):
        inputs = GmailSenderInputs(
            mail_subject="test",
            email_attachments=[{"url": "https://example.com/report", "filename": "custom.pdf"}],
        )

        assert inputs.email_attachments
        assert inputs.email_attachments[0].url == "https://example.com/report"
        assert inputs.email_attachments[0].filename == "custom.pdf"


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


class TestCreateRawMailMessageAttachments:
    def _decode_message(self, raw: dict):
        return message_from_bytes(base64.urlsafe_b64decode(raw["raw"]))

    def test_dict_attachment_uses_custom_filename(self, tmp_path, monkeypatch):
        def fake_download_to_local(url: str, output_dir, filename: str | None = None):
            path = output_dir / (filename or "downloaded.txt")
            path.write_text(f"downloaded from {url}")
            return path

        monkeypatch.setattr("engine.integrations.gmail.gmail_utils.get_output_dir", lambda: tmp_path)
        monkeypatch.setattr("engine.integrations.gmail.gmail_utils.download_to_local", fake_download_to_local)

        raw = create_raw_mail_message(
            subject="hi",
            sender_email_address="primary@example.com",
            body="body",
            attachments=[EmailAttachment(url="https://example.com/generated", filename="custom-name.txt")],
        )

        message = self._decode_message(raw)
        attachments = [part for part in message.walk() if part.get_content_disposition() == "attachment"]
        assert [part.get_filename() for part in attachments] == ["custom-name.txt"]


class TestGmailNeverdropSender:
    def test_tool_description_requires_non_empty_recipients(self):
        email_recipients = GMAIL_NEVERDROP_SENDER_TOOL_DESCRIPTION.tool_properties["email_recipients"]

        assert email_recipients["minItems"] == 1

    def test_input_schema_does_not_include_save_as_draft(self):
        input_schema = GmailNeverdropSender.get_inputs_schema()

        assert "save_as_draft" not in input_schema.model_fields

    @pytest.mark.asyncio
    async def test_sends_email(self):
        sender = GmailNeverdropSender(
            trace_manager=MagicMock(),
            component_attributes=ComponentAttributes(component_instance_name="gmail_neverdrop"),
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
