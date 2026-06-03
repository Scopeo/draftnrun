import base64

import pytest

from engine.integrations.outlook.outlook_sender import OutlookSenderInputs
from engine.integrations.outlook.outlook_utils import build_graph_mail_payload
from engine.integrations.utils import EmailAttachment


class TestOutlookSenderInputsValidation:
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
