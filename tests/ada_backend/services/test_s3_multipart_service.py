from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from ada_backend.schemas.s3_file_schema import CompletedPart, CompleteMultipartRequest, PresignPartRequest
from ada_backend.services.s3_files_service import (
    abort_multipart_upload,
    complete_multipart_upload,
    generate_presigned_part_urls,
    init_multipart_upload,
)

MODULE = "ada_backend.services.s3_files_service"


@pytest.fixture
def mock_s3_client():
    mock = MagicMock()
    with patch(f"{MODULE}.get_s3_client_and_ensure_bucket", return_value=mock):
        yield mock


class TestInitMultipartUpload:
    def test_creates_multipart_upload(self, mock_s3_client):
        mock_s3_client.create_multipart_upload.return_value = {"UploadId": "test-upload-id-123"}
        org_id = uuid4()

        result = init_multipart_upload(
            organization_id=org_id,
            filename="test.pdf",
            content_type="application/pdf",
            bucket_name="test-bucket",
        )

        assert result.upload_id == "test-upload-id-123"
        assert "test.pdf" in result.key
        assert str(org_id).replace("-", "_") in result.key
        mock_s3_client.create_multipart_upload.assert_called_once()
        call_kwargs = mock_s3_client.create_multipart_upload.call_args.kwargs
        assert call_kwargs["Bucket"] == "test-bucket"
        assert call_kwargs["Key"] == result.key
        assert call_kwargs["ContentType"] == "application/pdf"

    def test_raises_on_failure(self, mock_s3_client):
        mock_s3_client.create_multipart_upload.side_effect = Exception("access denied")

        with pytest.raises(ValueError, match="Failed to initiate multipart upload"):
            init_multipart_upload(
                organization_id=uuid4(),
                filename="test.pdf",
                content_type="application/pdf",
                bucket_name="test-bucket",
            )


class TestGeneratePresignedPartUrls:
    def test_presign_part_request_rejects_non_positive_part_count(self):
        with pytest.raises(ValueError, match="greater than 0"):
            PresignPartRequest(key="org/file.pdf", upload_id="upload-123", part_count=0)

    def test_generates_urls_for_all_parts(self, mock_s3_client):
        mock_s3_client.generate_presigned_url.side_effect = [
            f"https://s3.amazonaws.com/bucket/key?partNumber={i}&uploadId=uid" for i in range(1, 4)
        ]

        urls = generate_presigned_part_urls(
            key="org/file.pdf",
            upload_id="upload-123",
            part_count=3,
            bucket_name="test-bucket",
        )

        assert len(urls) == 3
        assert urls[0].part_number == 1
        assert urls[1].part_number == 2
        assert urls[2].part_number == 3
        for url in urls:
            assert url.presigned_url.startswith("https://")

        assert mock_s3_client.generate_presigned_url.call_count == 3
        for expected_part_number, presign_call in enumerate(
            mock_s3_client.generate_presigned_url.call_args_list, start=1
        ):
            assert presign_call.kwargs["ClientMethod"] == "upload_part"
            assert presign_call.kwargs["Params"] == {
                "Bucket": "test-bucket",
                "Key": "org/file.pdf",
                "UploadId": "upload-123",
                "PartNumber": expected_part_number,
            }
            assert presign_call.kwargs["ExpiresIn"] == 3600

    def test_raises_on_failure(self, mock_s3_client):
        mock_s3_client.generate_presigned_url.side_effect = Exception("expired")

        with pytest.raises(ValueError, match="Failed to generate presigned part URLs"):
            generate_presigned_part_urls(
                key="org/file.pdf",
                upload_id="upload-123",
                part_count=3,
                bucket_name="test-bucket",
            )


class TestCompleteMultipartUpload:
    def test_complete_request_rejects_empty_parts(self):
        with pytest.raises(ValueError, match="at least 1 item"):
            CompleteMultipartRequest(key="org/file.pdf", upload_id="upload-123", parts=[])

    def test_completed_part_rejects_invalid_values(self):
        with pytest.raises(ValueError, match="greater than 0"):
            CompletedPart(part_number=0, etag='"abc123"')

        with pytest.raises(ValueError, match="at least 1 character"):
            CompletedPart(part_number=1, etag="")

    def test_completes_upload_with_parts(self, mock_s3_client):
        parts = [
            CompletedPart(part_number=1, etag='"abc123"'),
            CompletedPart(part_number=2, etag='"def456"'),
        ]

        complete_multipart_upload(
            key="org/file.pdf",
            upload_id="upload-123",
            parts=parts,
            bucket_name="test-bucket",
        )

        mock_s3_client.complete_multipart_upload.assert_called_once()
        call_kwargs = mock_s3_client.complete_multipart_upload.call_args.kwargs
        assert call_kwargs["Bucket"] == "test-bucket"
        assert call_kwargs["Key"] == "org/file.pdf"
        assert call_kwargs["UploadId"] == "upload-123"
        assert call_kwargs["MultipartUpload"] == {
            "Parts": [
                {"PartNumber": 1, "ETag": '"abc123"'},
                {"PartNumber": 2, "ETag": '"def456"'},
            ]
        }

    def test_raises_on_failure(self, mock_s3_client):
        mock_s3_client.complete_multipart_upload.side_effect = Exception("invalid parts")

        with pytest.raises(ValueError, match="Failed to complete multipart upload"):
            complete_multipart_upload(
                key="org/file.pdf",
                upload_id="upload-123",
                parts=[CompletedPart(part_number=1, etag='"abc"')],
                bucket_name="test-bucket",
            )


class TestAbortMultipartUpload:
    def test_aborts_upload(self, mock_s3_client):
        abort_multipart_upload(
            key="org/file.pdf",
            upload_id="upload-123",
            bucket_name="test-bucket",
        )

        mock_s3_client.abort_multipart_upload.assert_called_once_with(
            Bucket="test-bucket",
            Key="org/file.pdf",
            UploadId="upload-123",
        )

    def test_raises_on_failure(self, mock_s3_client):
        mock_s3_client.abort_multipart_upload.side_effect = Exception("not found")

        with pytest.raises(ValueError, match="Failed to abort multipart upload"):
            abort_multipart_upload(
                key="org/file.pdf",
                upload_id="upload-123",
                bucket_name="test-bucket",
            )
