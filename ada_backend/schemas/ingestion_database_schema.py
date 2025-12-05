from pydantic import BaseModel


class ChunkData(BaseModel):
    data: dict
