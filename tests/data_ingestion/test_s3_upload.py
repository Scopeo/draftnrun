from io import BytesIO
from unittest.mock import MagicMock

import pytest

from data_ingestion.boto3_client import TRANSFER_CONFIG, upload_file_to_bucket


class TestUploadFileToBucket:
    def test_uses_upload_fileobj_with_transfer_config(self):
        mock_client = MagicMock()
        upload_file_to_bucket(mock_client, "test-bucket", "test-key", b"hello")

        mock_client.upload_fileobj.assert_called_once()
        args, kwargs = mock_client.upload_fileobj.call_args
        assert isinstance(args[0], BytesIO)
        assert args[0].read() == b"hello"
        assert args[1] == "test-bucket"
        assert args[2] == "test-key"
        assert kwargs["Config"] is TRANSFER_CONFIG

    def test_does_not_call_put_object(self):
        mock_client = MagicMock()
        upload_file_to_bucket(mock_client, "test-bucket", "test-key", b"data")
        mock_client.put_object.assert_not_called()

    def test_raises_on_upload_failure(self):
        mock_client = MagicMock()
        mock_client.upload_fileobj.side_effect = Exception("network timeout")

        with pytest.raises(ValueError, match="Failed to upload file"):
            upload_file_to_bucket(mock_client, "test-bucket", "test-key", b"data")

    def test_handles_empty_content(self):
        mock_client = MagicMock()
        upload_file_to_bucket(mock_client, "test-bucket", "test-key", b"")

        args, _ = mock_client.upload_fileobj.call_args
        assert args[0].read() == b""

    def test_handles_large_content(self):
        mock_client = MagicMock()
        large_content_size = TRANSFER_CONFIG.multipart_threshold + 1
        large_content = b"x" * large_content_size
        upload_file_to_bucket(mock_client, "test-bucket", "test-key", large_content)

        args, _ = mock_client.upload_fileobj.call_args
        assert len(args[0].read()) == large_content_size
