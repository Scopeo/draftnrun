from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from ada_backend.routers.s3_files_router import multipart_presign_parts
from ada_backend.schemas.s3_file_schema import PresignPartRequest

MODULE = "ada_backend.routers.s3_files_router"


class TestMultipartOrganizationKeyValidation:
    @pytest.mark.asyncio
    @patch(f"{MODULE}.generate_presigned_part_urls", return_value=[])
    async def test_presign_parts_accepts_sanitized_org_key(self, mock_generate_presigned_part_urls):
        organization_id = uuid4()
        sanitized_key = f"{str(organization_id).replace('-', '_')}/file.pdf"

        await multipart_presign_parts(
            organization_id=organization_id,
            request=PresignPartRequest(
                key=sanitized_key,
                upload_id="upload-123",
                part_count=2,
            ),
            auth=MagicMock(),
        )

        mock_generate_presigned_part_urls.assert_called_once_with(
            key=sanitized_key,
            upload_id="upload-123",
            part_count=2,
        )

    @pytest.mark.asyncio
    @patch(f"{MODULE}.generate_presigned_part_urls")
    async def test_presign_parts_rejects_cross_org_key(self, mock_generate_presigned_part_urls):
        organization_id = uuid4()
        other_organization_id = uuid4()

        with pytest.raises(HTTPException) as exc_info:
            await multipart_presign_parts(
                organization_id=organization_id,
                request=PresignPartRequest(
                    key=f"{str(other_organization_id).replace('-', '_')}/file.pdf",
                    upload_id="upload-123",
                    part_count=2,
                ),
                auth=MagicMock(),
            )

        assert exc_info.value.status_code == 403
        mock_generate_presigned_part_urls.assert_not_called()
