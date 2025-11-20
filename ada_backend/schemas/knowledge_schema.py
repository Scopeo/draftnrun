from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


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
    """
    Chunk model with required fields and support for additional fields.
    Used for building chunks with qdrant schema fields before persisting to SQL/Qdrant.
    """

    chunk_id: str
    file_id: str
    content: str
    last_edited_ts: str

    class Config:
        extra = "allow"


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
