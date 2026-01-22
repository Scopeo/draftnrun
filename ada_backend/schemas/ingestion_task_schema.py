from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from ada_backend.database import models as db
from data_ingestion.utils import DocumentReadingMode


class ResultType:
    """Simple result type categories."""

    PARTIAL_SUCCESS = "partial_success"
    ERROR = "error"


class TaskResultMetadata(BaseModel):
    """Structured metadata about task execution result."""

    message: str
    type: str


class IngestionTask(BaseModel):
    source_id: Optional[UUID] = None
    source_name: str
    source_type: db.SourceType
    status: db.TaskStatus
    result_metadata: Optional[TaskResultMetadata] = None


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
    url_pattern: Optional[str] = None
    update_existing: Optional[bool] = False
    query_filter: Optional[str] = None
    timestamp_filter: Optional[str] = None
    # Website ingestion fields
    url: Optional[str] = None  # Single URL to scrape
    follow_links: Optional[bool] = True  # Whether to follow links on the page
    max_depth: Optional[int] = 1  # Maximum depth for link following
    limit: Optional[int] = 100  # Maximum number of pages to crawl
    include_paths: Optional[list[str]] = None  # URL pathname regex patterns to include
    exclude_paths: Optional[list[str]] = None  # URL pathname regex patterns to exclude
    include_tags: Optional[list[str]] = None  # HTML tags to include in content extraction
    exclude_tags: Optional[list[str]] = None  # HTML tags to exclude from content extraction
    document_reading_mode: Optional[DocumentReadingMode] = DocumentReadingMode.STANDARD


class IngestionTaskUpdate(IngestionTask):
    id: UUID

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
