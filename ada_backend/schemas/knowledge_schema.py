from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class KnowledgeFileSummary(BaseModel):
    file_id: str
    document_title: Optional[str] = None
    chunk_count: int
    last_edited_ts: Optional[str] = None


class KnowledgeFileMetadata(BaseModel):
    file_id: str
    document_title: Optional[str] = None
    url: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    last_edited_ts: Optional[str] = None
    folder_name: Optional[str] = None


class KnowledgeChunk(BaseModel):
    chunk_id: str
    file_id: str
    content: str
    document_title: Optional[str] = None
    url: Optional[str] = None
    last_edited_ts: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    bounding_boxes: Optional[List[Dict[str, Any]]] = None
    processed_datetime: Optional[str] = Field(default=None, alias="_processed_datetime")

    class Config:
        allow_population_by_field_name = True

    @field_validator("processed_datetime", mode="before")
    @classmethod
    def _coerce_processed_datetime(cls, value: Any) -> Optional[str]:
        if isinstance(value, datetime):
            return value.isoformat()
        return value


class KnowledgeFileDetail(BaseModel):
    file: KnowledgeFileMetadata
    chunks: List[KnowledgeChunk]


class KnowledgeFileListResponse(BaseModel):
    total: int
    items: List[KnowledgeFileSummary]


class CreateKnowledgeChunkRequest(BaseModel):
    content: str
    chunk_id: Optional[str] = None
    last_edited_ts: Optional[str] = None


class UpdateKnowledgeChunkRequest(BaseModel):
    content: Optional[str] = None
    last_edited_ts: Optional[str] = None
