from fastapi import APIRouter, UploadFile, File, HTTPException, status, Depends
import logging
from typing import Annotated, Optional
from uuid import UUID, uuid4

from ada_backend.schemas.auth_schema import SupabaseUser
from ada_backend.routers.auth_router import user_has_access_to_organization_dependency, UserRights
from ada_backend.services.s3_files_service import upload_file_to_s3, delete_file_from_s3
from ada_backend.schemas.ingestion_task_schema import S3UploadedInformation

router = APIRouter(prefix="/files", tags=["S3 File Uploads"])
LOGGER = logging.getLogger(__name__)


@router.post("/{organization_id}/upload", response_model=list[S3UploadedInformation])
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
