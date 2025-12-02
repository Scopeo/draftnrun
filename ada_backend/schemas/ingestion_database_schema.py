from pydantic import BaseModel
from typing import Dict, Any


class ChunkData(BaseModel):
    data: dict


class UpdateChunk(BaseModel):
    update_data: Dict[str, Any]
