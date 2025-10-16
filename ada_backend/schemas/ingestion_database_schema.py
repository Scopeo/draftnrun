from pydantic import BaseModel
from typing import Dict, Any, List


class RowData(BaseModel):
    data: dict
    exists: bool


class PaginatedRowDataResponse(BaseModel):
    total: int
    page: int
    page_size: int
    total_pages: int
    items: List[RowData]


class UpdateRowRequest(BaseModel):
    update_data: Dict[str, Any]
    id_column_name: str
