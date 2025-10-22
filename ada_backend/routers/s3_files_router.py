from fastapi import APIRouter, UploadFile, File, HTTPException, status, Depends
import logging
from typing import Annotated, Optional
from uuid import UUID, uuid4

from ada_backend.schemas.auth_schema import SupabaseUser
from ada_backend.routers.auth_router import (
    user_has_access_to_organization_dependency,
    UserRights,
    user_has_access_to_organization_xor_verify_api_key,
)
from ada_backend.schemas.s3_file_schema import UploadFileRequest, S3UploadURL
from ada_backend.services.s3_files_service import (
    generate_s3_upload_presigned_urls_service,
    upload_file_to_s3,
    delete_file_from_s3,
)
from ada_backend.schemas.ingestion_task_schema import S3UploadedInformation

router = APIRouter(tags=["S3 File Uploads"])
LOGGER = logging.getLogger(__name__)


@router.post(
    "/organizations/{organization_id}/files/upload-urls",
    summary="Get S3 Upload Presigned URLs, authentication via user token or API key",
    response_model=list[S3UploadURL],
)
async def generate_s3_upload_presigned_urls(
    organization_id: UUID,
    upload_file_requests: list[UploadFileRequest],
    auth_ids: Annotated[
        tuple[UUID | None, UUID | None],
        Depends(user_has_access_to_organization_xor_verify_api_key(allowed_roles=UserRights.READER.value)),
    ],
) -> list[S3UploadURL]:
    """
    Generate S3 upload presigned URLs with flexible authentication.
    """
    user_id, api_key_id = auth_ids  # One is always None
    try:
        return generate_s3_upload_presigned_urls_service(organization_id, upload_file_requests)
    except Exception as e:
        LOGGER.exception(
            "Failed to generate S3 presigned URLs for organization %s (count=%s)",
            organization_id,
            len(upload_file_requests),
        )
        raise HTTPException(status_code=500, detail="Internal Server Error") from e


# TODO: Refactor endpoint to be more RESTful:
#       use POST /organizations/{organization_id}/files
#       instead of /files/{organization_id}/upload
@router.post("/files/{organization_id}/upload", response_model=list[S3UploadedInformation])
async def upload_files(
    organization_id: UUID,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.WRITER.value))
    ],
    files: Annotated[Optional[list[UploadFile]], File()] = None,
):
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")

    uploaded_files = []
    try:
        for file in files:
            content_bytes = await file.read()
            s3_filename = f"{organization_id}/{uuid4()}_{file.filename}"
            uploaded_files.append(upload_file_to_s3(file_name=s3_filename, byte_content=content_bytes))
        return uploaded_files
    except Exception as e:
        LOGGER.exception(
            "Failed to upload files to S3 for organization %s (count=%s)",
            organization_id,
            len(files) if files else 0,
        )
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {e}")


# TODO: Refactor endpoint to be more RESTful:
#       use DELETE /organizations/{organization_id}/files
#       instead of /files/{organization_id}/upload
@router.post("/{organization_id}/delete", status_code=status.HTTP_204_NO_CONTENT)
async def delete_files(
    organization_id: UUID,
    user: Annotated[
        SupabaseUser, Depends(user_has_access_to_organization_dependency(allowed_roles=UserRights.WRITER.value))
    ],
    file_ids: list[str],
):
    if not user.id:
        raise HTTPException(status_code=400, detail="User ID not found")

    try:
        for file_id in file_ids:
            delete_file_from_s3(key=file_id)
    except Exception as e:
        LOGGER.exception(
            "Failed to delete files from S3 for organization %s (file_ids=%s)",
            organization_id,
            file_ids,
        )
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {e}")
