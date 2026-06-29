from types import SimpleNamespace
from uuid import uuid4

import pytest

from ada_backend.services import s3_files_service


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
