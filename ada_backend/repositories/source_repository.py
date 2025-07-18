from uuid import UUID
from typing import Optional
import logging
from datetime import datetime

from sqlalchemy.orm import Session

from ada_backend.database import models as db

LOGGER = logging.getLogger(__name__)


def get_data_source_by_id(
    session_sql_alchemy: Session,
    source_id: UUID,
) -> Optional[db.DataSource]:
    """Retrieve a source by its id"""
    return (
        session_sql_alchemy.query(db.DataSource)
        .filter(
            db.DataSource.id == source_id,
        )
        .first()
    )


def get_data_source_by_org_id(
    session_sql_alchemy: Session,
    organization_id: UUID,
    source_id: UUID,
) -> Optional[db.DataSource]:
    """Retrieve a source by its id and organization id"""
    return (
        session_sql_alchemy.query(db.DataSource)
        .filter(
            db.DataSource.id == source_id,
            db.DataSource.organization_id == organization_id,
        )
        .first()
    )


def get_data_source_by_name_and_org(
    session_sql_alchemy: Session,
    organization_id: UUID,
    source_name: str,
) -> Optional[db.DataSource]:
    """Retrieve a source by its name and organization id"""
    if isinstance(organization_id, str):
        organization_id = UUID(organization_id)
    return (
        session_sql_alchemy.query(db.DataSource)
        .filter(
            db.DataSource.organization_id == organization_id,
            db.DataSource.name == source_name,
        )
        .first()
    )


def get_sources(
    session_sql_alchemy: Session,
    organization_id: UUID,
) -> list[db.DataSource]:
    """"""
    if isinstance(organization_id, str):
        organization_id = UUID(organization_id)
    query = session_sql_alchemy.query(db.DataSource).filter(db.DataSource.organization_id == organization_id)
    sources = query.all()
    return sources


def create_source(
    session: Session,
    organization_id: UUID,
    source_name: str,
    source_type: db.SourceType,
    database_table_name: str,
    database_schema: Optional[str] = None,
    qdrant_collection_name: Optional[str] = None,
    qdrant_schema: Optional[dict] = None,
    embedding_model_reference: Optional[str] = None,
) -> UUID:
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
    session.commit()
    return source_data_create.id


def upsert_source(
    session_sql_alchemy: Session,
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
    """"""
    existing_source = (
        session_sql_alchemy.query(db.DataSource)
        .filter(
            db.DataSource.organization_id == organization_id,
            db.DataSource.id == source_id,
        )
        .first()
    )
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
        existing_source.last_ingestion_time = datetime.utcnow()
    session_sql_alchemy.commit()


def delete_source(
    session_sql_alchemy: Session,
    organization_id: UUID,
    source_id: UUID,
) -> None:
    LOGGER.info(f"Deleting source with id {source_id} for organization {organization_id}")
    session_sql_alchemy.query(db.DataSource).filter(
        db.DataSource.organization_id == organization_id, db.DataSource.id == source_id
    ).delete()
    session_sql_alchemy.commit()


def check_source_name_exists(
    session_sql_alchemy: Session,
    organization_id: UUID,
    source_name: str,
) -> bool:
    """
    Check if a source with the given name already exists for the organization.

    Args:
        session_sql_alchemy (Session): SQLAlchemy session
        organization_id (UUID): Organization ID
        source_name (str): Source name to check

    Returns:
        bool: True if a source with the same name exists, False otherwise
    """
    if isinstance(organization_id, str):
        organization_id = UUID(organization_id)

    existing_source = (
        session_sql_alchemy.query(db.DataSource)
        .filter(
            db.DataSource.organization_id == organization_id,
            db.DataSource.name == source_name,
        )
        .first()
    )

    return existing_source is not None
