from uuid import UUID
from typing import Optional
import json

from pydantic import BaseModel, ConfigDict

from ada_backend.database import models as db

JSON_INGESTION_TASK_QUEUE_DESCRIPTION = {
    "source_name": "My source name",
    "source_type": "remote_local",
    "status": "pending",
    "source_attributes": {
        "access_token": None,
        "path": "/user/files/",
        "description_remote_folder": [
            {
                "path": "/user/files/doc1.pdf",
                "name": "doc1.pdf",
                "content": None,
                "last_edited_ts": "2024-06-01T12:00:00Z",
                "metadata": {"author": "User"},
            },
            {
                "path": "/user/files/doc2.pdf",
                "name": "doc2.pdf",
                "content": None,
                "last_edited_ts": "2024-06-02T13:00:00Z",
                "metadata": {"author": "User"},
            },
        ],
        "folder_id": "abc123",
        "source_db_url": None,
        "source_table_name": None,
        "id_column_name": None,
        "text_column_names": None,
        "source_schema_name": None,
        "metadata_column_names": None,
        "timestamp_column_name": None,
        "is_sync_enabled": False,
    },
}

JSON_STRING_INGESTION_TASK_QUEUE_DESCRIPTION = json.dumps(JSON_INGESTION_TASK_QUEUE_DESCRIPTION).replace('"', '\\"')


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
    description_remote_folder: Optional[list[RemoteFile]] = None
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
    s3_sanitized_name: str
