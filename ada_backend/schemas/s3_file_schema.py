from pydantic import BaseModel, Field, conint, conlist, constr


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
    part_number: conint(gt=0)
    etag: constr(min_length=1)


class CompleteMultipartRequest(BaseModel):
    key: str
    upload_id: str
    parts: conlist(CompletedPart, min_length=1)


class AbortMultipartRequest(BaseModel):
    key: str
    upload_id: str
