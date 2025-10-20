from pydantic import BaseModel
from typing import Dict, Any, List


class ChunkData(BaseModel):
    data: dict


class PaginatedChunkDataResponse(BaseModel):
    total: int
    page: int
    page_size: int
    total_pages: int
    items: List[ChunkData]


class UpdateChunk(BaseModel):
    update_data: Dict[str, Any]
