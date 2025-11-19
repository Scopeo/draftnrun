from uuid import UUID

from sqlalchemy.orm import Session

from engine.storage_service.local_service import SQLLocalService
from ingestion_script.utils import get_sanitize_names
from engine.storage_service.db_utils import DBDefinition
from settings import settings
from ada_backend.repositories.source_repository import get_data_source_by_id
from ada_backend.services.errors import SourceNotFound, ChunkSourceMismatchError, ChunkNotFoundError


def get_sql_local_service_for_ingestion() -> SQLLocalService:
    return SQLLocalService(engine_url=settings.INGESTION_DB_URL)


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
