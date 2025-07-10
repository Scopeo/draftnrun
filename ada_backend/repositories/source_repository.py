from uuid import UUID
from typing import Optional
import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ada_backend.database import models as db

LOGGER = logging.getLogger(__name__)


async def get_data_source_by_id(
    session_sql_alchemy: AsyncSession,
    source_id: UUID,
) -> Optional[db.DataSource]:
    """Retrieve a source by its id asynchronously"""
    stmt = select(db.DataSource).where(
        db.DataSource.id == source_id,
    )
    result = await session_sql_alchemy.execute(stmt)
    return result.scalar_one_or_none()


async def get_data_source_by_org_id(
    session_sql_alchemy: AsyncSession,
    organization_id: UUID,
    source_id: UUID,
) -> Optional[db.DataSource]:
    """Retrieve a source by its id and organization id asynchronously"""
    stmt = select(db.DataSource).where(
        db.DataSource.id == source_id,
        db.DataSource.organization_id == organization_id,
    )
    result = await session_sql_alchemy.execute(stmt)
    return result.scalar_one_or_none()


async def get_sources(
    session_sql_alchemy: AsyncSession,
    organization_id: UUID,
) -> list[db.DataSource]:
    """Asynchronously retrieves data sources for a given organization."""
    if isinstance(organization_id, str):
        organization_id = UUID(organization_id)
    stmt = select(db.DataSource).where(db.DataSource.organization_id == organization_id)
    result = await session_sql_alchemy.execute(stmt)
    sources = result.scalars().all()
    return sources


async def create_source(
    session: AsyncSession,
    organization_id: UUID,
    source_name: str,
    source_type: db.SourceType,
    database_table_name: str,
    database_schema: Optional[str] = None,
    qdrant_collection_name: Optional[str] = None,
    qdrant_schema: Optional[dict] = None,
    embedding_model_reference: Optional[str] = None,
) -> UUID:
    """Asynchronously creates a new data source."""
    source_data_create = db.DataSource(
        name=source_name,
        type=source_type,
        organization_id=organization_id,
        database_schema=database_schema,
        database_table_name=database_table_name,
        qdrant_collection_name=qdrant_collection_name,
        qdrant_schema=qdrant_schema,
        embedding_model_reference=embedding_model_reference,
    )
    session.add(source_data_create)
    await session.commit()
    return source_data_create.id


async def upsert_source(
    session_sql_alchemy: AsyncSession,
    organization_id: UUID,
    source_id: UUID,
    source_name: str,
    source_type: db.SourceType,
    database_table_name: str,
    database_schema: Optional[str] = None,
    qdrant_collection_name: Optional[str] = None,
    qdrant_schema: Optional[dict] = None,
    embedding_model_reference: Optional[str] = None,
) -> None:
    """Asynchronously updates an existing data source."""
    stmt = select(db.DataSource).where(
        db.DataSource.organization_id == organization_id,
        db.DataSource.id == source_id,
    )
    existing_source = (await session_sql_alchemy.execute(stmt)).scalar_one_or_none()
    if existing_source:
        if source_name:
            existing_source.name = source_name
        if source_type:
            existing_source.type = source_type
        if embedding_model_reference:
            existing_source.embedding_model_reference = embedding_model_reference
        existing_source.database_schema = database_schema
        existing_source.database_table_name = database_table_name
        existing_source.qdrant_collection_name = qdrant_collection_name
        existing_source.qdrant_schema = qdrant_schema
    await session_sql_alchemy.commit()


async def delete_source(
    session_sql_alchemy: AsyncSession,
    organization_id: UUID,
    source_id: UUID,
) -> None:
    """Asynchronously deletes a data source."""
    LOGGER.info(f"Deleting source with id {source_id} for organization {organization_id}")
    stmt = select(db.DataSource).where(db.DataSource.organization_id == organization_id, db.DataSource.id == source_id)
    source_to_delete = (await session_sql_alchemy.execute(stmt)).scalar_one_or_none()
    if source_to_delete:
        await session_sql_alchemy.delete(source_to_delete)
        await session_sql_alchemy.commit()
