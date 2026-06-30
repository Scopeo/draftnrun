from types import SimpleNamespace
from uuid import uuid4

import pytest

from ada_backend.services import s3_files_service
from ada_backend.schemas.s3_file_schema import UploadFileRequest


def test_generate_s3_download_presigned_url_requires_organization_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    organization_id = uuid4()
    mock_client = SimpleNamespace()

    def mock_presign(s3_client, key, bucket_name):
        return f"https://s3.example.com/{key}"

    monkeypatch.setattr(s3_files_service, "get_s3_client_and_ensure_bucket", lambda bucket_name: mock_client)
    monkeypatch.setattr(s3_files_service, "generate_presigned_download_url", mock_presign)

    response = s3_files_service.generate_s3_download_presigned_url_service(
        organization_id=organization_id,
        key=f"{organization_id}/file.pdf",
        bucket_name="bucket",
    )

    assert response.key == f"{organization_id}/file.pdf"
    assert response.url == f"https://s3.example.com/{organization_id}/file.pdf"


def test_generate_s3_download_presigned_url_rejects_other_organization_key() -> None:
    with pytest.raises(s3_files_service.S3DownloadKeyValidationError, match="does not belong"):
        s3_files_service.generate_s3_download_presigned_url_service(
            organization_id=uuid4(),
            key=f"{uuid4()}/file.pdf",
            bucket_name="bucket",
        )


def test_generate_s3_upload_presigned_url_preserves_organization_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    organization_id = uuid4()
    fixed_upload_id = uuid4()
    mock_client = SimpleNamespace()

    monkeypatch.setattr(s3_files_service, "get_s3_client_and_ensure_bucket", lambda bucket_name: mock_client)
    monkeypatch.setattr(s3_files_service, "uuid4", lambda: fixed_upload_id)
    monkeypatch.setattr(
        s3_files_service,
        "generate_presigned_upload_url",
        lambda s3_client, key, content_type, bucket_name: f"https://s3.example.com/{key}",
    )

    response = s3_files_service.generate_s3_upload_presigned_urls_service(
        organization_id=organization_id,
        upload_file_requests=[UploadFileRequest(filename="Sample File.pdf", content_type="application/pdf")],
        bucket_name="bucket",
    )

    assert len(response) == 1
    expected_suffix = f"{str(fixed_upload_id).replace('-', '_')}_sample_file.pdf"
    assert response[0].key == f"{organization_id}/{expected_suffix}"
    assert response[0].presigned_url == f"https://s3.example.com/{organization_id}/{expected_suffix}"


def test_upload_file_to_s3_preserves_organization_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    organization_id = uuid4()
    uploaded = {}

    monkeypatch.setattr(
        s3_files_service,
        "get_s3_client_and_ensure_bucket",
        lambda bucket_name: SimpleNamespace(name="mock-client"),
    )

    def mock_upload(s3_client, bucket_name, key, byte_content):
        uploaded["key"] = key
        uploaded["byte_content"] = byte_content

    monkeypatch.setattr(s3_files_service, "upload_file_to_bucket", mock_upload)

    response = s3_files_service.upload_file_to_s3(
        file_name=f"{organization_id}/My File.pdf",
        byte_content=b"pdf-bytes",
        bucket_name="bucket",
    )

    assert response.s3_path_file == f"{organization_id}/my_file.pdf"
    assert uploaded["key"] == f"{organization_id}/my_file.pdf"
    assert uploaded["byte_content"] == b"pdf-bytes"
