from pydantic import BaseModel
from typing import Dict, Any


class RowInfo(BaseModel):
    row_id: int
    data: dict
    exists: bool


class UpdateRowRequest(BaseModel):
    update_data: Dict[str, Any]
    id_column_name: str
