import base64

import pytest

from engine.integrations.outlook.outlook_sender import OUTLOOK_SENDER_TOOL_DESCRIPTION, OutlookSenderInputs
from engine.integrations.outlook.outlook_utils import build_graph_mail_payload
from engine.integrations.utils import EmailAttachment


class TestOutlookSenderInputsValidation:
    def test_string_attachment_is_accepted(self):
        inputs = OutlookSenderInputs(
            mail_subject="test",
            email_attachments=["https://example.com/report"],
        )

        assert inputs.email_attachments
        assert inputs.email_attachments[0].url == "https://example.com/report"
        assert inputs.email_attachments[0].filename == "report"

    def test_json_string_attachment_list_is_accepted(self):
        inputs = OutlookSenderInputs(
            mail_subject="test",
            email_attachments='[{"url": "https://example.com/report.pdf", "filename": "report.pdf"}]',
        )

        assert inputs.email_attachments
        assert inputs.email_attachments[0].url == "https://example.com/report.pdf"
        assert inputs.email_attachments[0].filename == "report.pdf"

    def test_dict_attachment_is_accepted(self):
        inputs = OutlookSenderInputs(
            mail_subject="test",
            email_attachments=[{"url": "https://example.com/report", "filename": "custom.pdf"}],
        )

        assert inputs.email_attachments
        assert inputs.email_attachments[0].url == "https://example.com/report"
        assert inputs.email_attachments[0].filename == "custom.pdf"

    def test_dict_attachment_requires_url_and_filename(self):
        with pytest.raises(ValueError, match="filename"):
            OutlookSenderInputs(
                mail_subject="test",
                email_attachments=[{"url": "https://example.com/report"}],
            )

    def test_dict_attachment_requires_url_or_path(self):
        with pytest.raises(ValueError, match="url.*path"):
            OutlookSenderInputs(
                mail_subject="test",
                email_attachments=[{"filename": "custom.pdf"}],
            )

    def test_path_attachment_is_accepted(self):
        inputs = OutlookSenderInputs(
            mail_subject="test",
            email_attachments=[{"path": "report.pdf", "filename": "custom.pdf"}],
        )

        assert inputs.email_attachments
        assert inputs.email_attachments[0].path == "report.pdf"
        assert inputs.email_attachments[0].filename == "custom.pdf"

    def test_attachment_tool_schema_does_not_use_unions(self):
        schema = OUTLOOK_SENDER_TOOL_DESCRIPTION.tool_properties["email_attachments"]["items"]

        assert "oneOf" not in schema
        assert "anyOf" not in schema
        assert schema["type"] == "object"
        assert schema["properties"]["url"]["type"] == "string"
        assert schema["properties"]["path"]["type"] == "string"
        assert schema["properties"]["filename"]["type"] == "string"
        assert schema["required"] == ["filename"]
        assert schema["additionalProperties"] is False
        assert schema["minProperties"] == 2
        assert schema["maxProperties"] == 2

    def test_attachment_input_schema_does_not_use_unions(self):
        schema = OutlookSenderInputs.model_json_schema()["properties"]["email_attachments"]

        assert "oneOf" not in schema
        assert "anyOf" not in schema
        assert "oneOf" not in schema["items"]
        assert "anyOf" not in schema["items"]


class TestBuildGraphMailPayloadAttachments:
    def test_dict_attachment_uses_custom_filename(self, tmp_path, monkeypatch):
        def fake_download_to_local(url: str, output_dir, filename: str | None = None):
            path = output_dir / (filename or "downloaded.txt")
            path.write_text(f"downloaded from {url}")
            return path

        monkeypatch.setattr("engine.integrations.outlook.outlook_utils.get_output_dir", lambda: tmp_path)
        monkeypatch.setattr("engine.integrations.outlook.outlook_utils.download_to_local", fake_download_to_local)

        payload = build_graph_mail_payload(
            subject="hi",
            body="body",
            attachments=[EmailAttachment(url="https://example.com/generated", filename="custom-name.txt")],
        )

        attachment = payload["attachments"][0]
        assert attachment["name"] == "custom-name.txt"
        assert attachment["contentType"] == "text/plain"
        assert base64.b64decode(attachment["contentBytes"]).decode() == "downloaded from https://example.com/generated"

    def test_plain_url_attachment_uses_url_path_filename_without_query(self, tmp_path, monkeypatch):
        captured_filenames: list[str | None] = []

        def fake_download_to_local(url: str, output_dir, filename: str | None = None):
            captured_filenames.append(filename)
            path = output_dir / "downloaded.txt"
            path.write_text(f"downloaded from {url}")
            return path

        monkeypatch.setattr("engine.integrations.outlook.outlook_utils.get_output_dir", lambda: tmp_path)
        monkeypatch.setattr("engine.integrations.outlook.outlook_utils.download_to_local", fake_download_to_local)

        payload = build_graph_mail_payload(
            subject="hi",
            body="body",
            attachments=["https://example.com/report.txt?signature=secret"],
        )

        assert captured_filenames == [None]
        assert payload["attachments"][0]["name"] == "downloaded.txt"
