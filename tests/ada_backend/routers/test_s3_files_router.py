from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from ada_backend.routers.s3_files_router import generate_file_download_url
from ada_backend.schemas.auth_schema import SupabaseUser
from ada_backend.schemas.s3_file_schema import FileDownloadURLRequest
from ada_backend.services.s3_files_service import FileDownloadKeyValidationError


def _make_user() -> SupabaseUser:
    return SupabaseUser(id=uuid4(), email="user@example.com", token="token")


class TestGenerateFileDownloadUrl:
    @pytest.mark.asyncio
    @patch(
        "ada_backend.routers.s3_files_router.generate_file_download_url_service",
        side_effect=FileDownloadKeyValidationError("File key does not belong to this organization"),
    )
    async def test_returns_safe_400_for_invalid_key(self, _mock_service):
        with pytest.raises(HTTPException) as exc_info:
            await generate_file_download_url(
                organization_id=uuid4(),
                download_file_request=FileDownloadURLRequest(key=f"{uuid4()}/file.pdf"),
                user=_make_user(),
            )

        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == "Invalid file key"

    @pytest.mark.asyncio
    @patch(
        "ada_backend.routers.s3_files_router.generate_file_download_url_service",
        side_effect=ValueError("Couldn't get a presigned download URL: aws credentials missing"),
    )
    async def test_does_not_leak_internal_value_error_details(self, _mock_service):
        with pytest.raises(HTTPException) as exc_info:
            await generate_file_download_url(
                organization_id=uuid4(),
                download_file_request=FileDownloadURLRequest(key=f"{uuid4()}/file.pdf"),
                user=_make_user(),
            )

        assert exc_info.value.status_code == 500
        assert exc_info.value.detail == "Internal Server Error"
