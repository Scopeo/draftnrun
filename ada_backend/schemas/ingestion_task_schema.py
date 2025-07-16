from uuid import UUID
from typing import Optional

from pydantic import BaseModel, ConfigDict

from ada_backend.database import models as db


class IngestionTask(BaseModel):
    source_name: str
    source_type: db.SourceType
    status: db.TaskStatus


class RemoteFile(BaseModel):
    path: str
    name: str
    s3_path: str | None = None
    last_edited_ts: str
    metadata: dict = {}


class SourceAttributes(BaseModel):
    access_token: Optional[str] = None
    path: Optional[str] = None
    list_of_files_from_local_folder: Optional[list[RemoteFile]] = None
    folder_id: Optional[str] = None
    source_db_url: Optional[str] = None
    source_table_name: Optional[str] = None
    id_column_name: Optional[str] = None
    text_column_names: Optional[list[str]] = None
    source_schema_name: Optional[str] = None
    chunk_size: Optional[int] = None
    chunk_overlap: Optional[int] = None
    metadata_column_names: Optional[list[str]] = None
    timestamp_column_name: Optional[str] = None
    url_column_name: Optional[str] = None
    replace_existing: Optional[bool] = False
    query_filter: Optional[str] = None


class IngestionTaskUpdate(IngestionTask):
    id: UUID
    source_id: Optional[UUID] = None

    model_config = ConfigDict(
        from_attributes=True,
        json_encoders={UUID: str},
    )


class IngestionTaskResponse(IngestionTaskUpdate):
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class IngestionTaskQueue(IngestionTask):
    source_attributes: SourceAttributes


class S3UploadedInformation(BaseModel):
    s3_path_file: str
