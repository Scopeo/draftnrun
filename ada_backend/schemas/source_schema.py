from typing import Optional
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, ConfigDict
from ada_backend.database import models as db


class DataSourceSchema(BaseModel):
    name: str
    type: db.SourceType
    database_schema: Optional[str] = None
    database_table_name: str
    qdrant_collection_name: Optional[str] = None
    qdrant_schema: Optional[dict] = None
    embedding_model_reference: Optional[str] = None

    model_config = ConfigDict(
        from_attributes=True, json_encoders={datetime: lambda dt: dt.isoformat() if dt else None}
    )


class DataSourceUpdateSchema(DataSourceSchema):
    id: Optional[UUID] = None


class DataSourceSchemaResponse(DataSourceUpdateSchema):
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    last_ingestion_time: Optional[datetime] = None
