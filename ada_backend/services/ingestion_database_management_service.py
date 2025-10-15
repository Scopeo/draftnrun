from engine.storage_service.local_service import SQLLocalService

from settings import settings


def get_sql_local_service_for_ingestion() -> SQLLocalService:
    return SQLLocalService(engine_url=settings.INGESTION_DB_URL)
