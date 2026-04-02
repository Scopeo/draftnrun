from typing import Optional
from uuid import UUID

from engine.storage_service.db_utils import DBDefinition
from engine.storage_service.local_service import SQLLocalService
from ingestion_script.utils import get_sanitize_names
from settings import settings

_ingestion_service: Optional[SQLLocalService] = None


def get_sql_local_service_for_ingestion() -> SQLLocalService:
    global _ingestion_service
    if _ingestion_service is None:
        _ingestion_service = SQLLocalService(engine_url=settings.INGESTION_DB_URL)
    return _ingestion_service


def create_table_in_ingestion_db(
    organization_id: UUID,
    source_id: UUID,
    table_definition: DBDefinition,
) -> tuple[str, DBDefinition]:
    sql_local_service = get_sql_local_service_for_ingestion()
    schema_name, table_name, qdrant_collection_name = get_sanitize_names(
        organization_id=str(organization_id),
        embedding_model_reference=None,
    )
    sql_local_service.create_table(
        table_name=table_name,
        table_definition=table_definition,
        schema_name=schema_name,
    )
    return table_name, table_definition
