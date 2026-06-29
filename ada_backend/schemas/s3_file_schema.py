from pydantic import BaseModel


class UploadFileRequest(BaseModel):
    filename: str
    content_type: str


class S3UploadURL(BaseModel):
    filename: str
    presigned_url: str
    key: str
    content_type: str


class S3DownloadURLRequest(BaseModel):
    key: str


class S3DownloadURL(BaseModel):
    key: str
    url: str
