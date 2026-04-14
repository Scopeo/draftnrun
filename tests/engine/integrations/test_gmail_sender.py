from engine.integrations.gmail.gmail_sender import GmailSenderInputs
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
