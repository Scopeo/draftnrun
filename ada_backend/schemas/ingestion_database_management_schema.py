from pydantic import BaseModel
from typing import Dict, Any


class RowData(BaseModel):
    data: dict
    exists: bool


class UpdateRowRequest(BaseModel):
    update_data: Dict[str, Any]
    id_column_name: str
