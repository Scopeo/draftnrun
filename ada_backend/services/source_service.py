import logging
from typing import List
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from ada_backend.repositories.source_repository import (
    create_source,
    delete_source,
    get_data_source_by_org_id,
    get_sources,
    upsert_source,
)
from ada_backend.schemas.source_schema import (
    DataSourceSchema,
    DataSourceSchemaResponse,
    DataSourceUpdateSchema,
)
from engine.qdrant_service import QdrantCollectionSchema, QdrantService
from engine.storage_service.local_service import SQLLocalService
from settings import settings

LOGGER = logging.getLogger(__name__)


async def get_sources_by_organization(
    session: AsyncSession,
    organization_id: UUID,
) -> List[DataSourceSchemaResponse]:
    """
    Get all sources for an organization through the service layer asynchronously.

    Args:
        session (AsyncSession): SQLAlchemy asynchronous session
        organization_id (UUID): ID of the organization to get sources for

    Returns:
        List[GetDataSourceSchema]: List of sources belonging to the organization
    """
    try:
        sources = await get_sources(session, organization_id)
        return [
            DataSourceSchemaResponse(
                id=source.id,
                name=source.name,
                type=source.type,
                organization_id=source.organization_id,
                database_schema=source.database_schema,
                database_table_name=source.database_table_name,
                qdrant_collection_name=source.qdrant_collection_name,
                qdrant_schema=source.qdrant_schema,
                embedding_model_reference=source.embedding_model_reference,
                created_at=str(source.created_at),
                updated_at=str(source.updated_at),
                last_ingestion_time=str(source.last_ingestion_time) if source.last_ingestion_time else None,
            )
            for source in sources
        ]
    except Exception as e:
        LOGGER.error(f"Error in get_sources_by_organization: {str(e)}")
        raise ValueError(f"Failed to get sources: {str(e)}") from e


async def create_source_by_organization(
    session: AsyncSession,
    organization_id: UUID,
    source_data: DataSourceSchema,
) -> UUID:
    """
    Create a new source for an organization asynchronously.
    Args:
        session (AsyncSession): SQLAlchemy asynchronous session
        organization_id (UUID): ID of the organization
        source_data (DataSourceSchema): Source data to create
    Returns:
        None
    """
    try:
        source_id = await create_source(
            session,
            organization_id,
            source_data.name,
            source_data.type,
            source_data.database_table_name,
            source_data.database_schema,
            source_data.qdrant_collection_name,
            source_data.qdrant_schema,
            source_data.embedding_model_reference,
        )

        LOGGER.info(f"Source {source_data.name} created for organization {organization_id}")
        return source_id

    except Exception as e:
        LOGGER.error(f"Error in create_source_by_organization: {str(e)}")
        raise ValueError(f"Failed to create source: {str(e)}") from e


async def upsert_source_by_organization(
    session: AsyncSession,
    organization_id: UUID,
    source_data: DataSourceUpdateSchema,
) -> None:
    """
    Create a new source for an organization asynchronously.

    Args:
        session (AsyncSession): SQLAlchemy asynchronous session
        organization_id (UUID): ID of the organization
        source_data (DataSourceSchema): Source data to create

    Returns:
        None
    """
    try:
        return await upsert_source(
            session,
            organization_id,
            source_data.id,
            source_data.name,
            source_data.type,
            source_data.database_table_name,
            source_data.database_schema,
            source_data.qdrant_collection_name,
            source_data.qdrant_schema,
            source_data.embedding_model_reference,
        )
    except Exception as e:
        LOGGER.error(f"Error in upsert_source_by_organization: {str(e)}")
        raise ValueError(f"Failed to upsert source: {str(e)}") from e


async def delete_source_service(
    session: AsyncSession,
    organization_id: UUID,
    source_id: UUID,
) -> None:
    """Delete sources with matching name in the organization asynchronously."""
    try:

        source = await get_data_source_by_org_id(session, organization_id, source_id)
        if not source:
            raise ValueError(f"Source {source_id} not found")

        # TODO change snowflake to db service when ingestion script is updated
        # TODO enhance security by double checking deletion rights
        if source.qdrant_collection_name and source.qdrant_schema:
            LOGGER.info(f"Deleting Qdrant collection {source.qdrant_collection_name}")
            qdrant_service = QdrantService.from_defaults(
                default_collection_schema=QdrantCollectionSchema(**source.qdrant_schema),
            )

            await qdrant_service.adelete_collection(
                collection_name=source.qdrant_collection_name,
            )
            LOGGER.info(f"Qdrant collection {source.qdrant_collection_name} deleted")
        if source.database_table_name:
            LOGGER.info(f"Deleting table {source.database_table_name}")
            # TODO: put in async the SQLLocalService
            db_service = SQLLocalService(engine_url=settings.INGESTION_DB_URL)
            db_service.drop_table(
                table_name=source.database_table_name,
                schema_name=source.database_schema,
            )
            LOGGER.info(f"Table {source.database_table_name} deleted")
            await delete_source(session, organization_id, source_id) # Await the repository call
    except Exception as e:
        LOGGER.error(f"Error in delete_source_by_id: {str(e)}")
        raise ValueError(f"Failed to delete source: {str(e)}") from e