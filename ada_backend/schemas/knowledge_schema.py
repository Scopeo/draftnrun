from typing import List, Optional

from pydantic import BaseModel


class KnowledgeDocumentOverview(BaseModel):
    document_id: str
    document_title: Optional[str] = None
    chunk_count: int
    last_edited_ts: Optional[str] = None


class KnowledgeDocumentMetadata(BaseModel):
    document_id: str
    document_title: Optional[str] = None
    url: Optional[str] = None
    last_edited_ts: Optional[str] = None
    metadata: Optional[dict] = None


class KnowledgeChunk(BaseModel):
    """
    Chunk model with required fields and support for additional fields.
    Used for building chunks with qdrant schema fields before persisting to SQL/Qdrant.
    """

    chunk_id: str
    order: int
    content: str
    last_edited_ts: str
    document_id: str
    document_title: Optional[str] = None
    url: Optional[str] = None
    metadata: Optional[dict] = None

    class Config:
        extra = "ignore"


class KnowledgeDocumentWithChunks(BaseModel):
    document: KnowledgeDocumentMetadata
    chunks: List[KnowledgeChunk]
    total_chunks: int


class KnowledgeDocumentsListResponse(BaseModel):
    total: int
    items: List[KnowledgeDocumentOverview]
