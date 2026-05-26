from typing import Annotated

from pydantic import BaseModel, Field


class UploadFileRequest(BaseModel):
    filename: str
    content_type: str


class S3UploadURL(BaseModel):
    filename: str
    presigned_url: str
    key: str
    content_type: str


class MultipartInitRequest(BaseModel):
    filename: str
    content_type: str


class MultipartInitResponse(BaseModel):
    upload_id: str
    key: str


class PresignPartRequest(BaseModel):
    key: str
    upload_id: str
    part_count: int = Field(..., gt=0)


class PresignedPartURL(BaseModel):
    part_number: int
    presigned_url: str


class CompletedPart(BaseModel):
    part_number: Annotated[int, Field(gt=0)]
    etag: Annotated[str, Field(min_length=1)]


class CompleteMultipartRequest(BaseModel):
    key: str
    upload_id: str
    parts: Annotated[list[CompletedPart], Field(min_length=1)]


class AbortMultipartRequest(BaseModel):
    key: str
    upload_id: str
