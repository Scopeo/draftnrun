from uuid import UUID
from typing import Optional
import logging

from sqlalchemy.orm import Session

from ada_backend.database import models as db

from ada_backend.repositories.organization_repository import (
    upsert_organization_secret,
)
from ada_backend.schemas.ingestion_task_schema import SourceAttributes

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
    attributes: Optional[SourceAttributes] = None,
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
    session.refresh(source_data_create)

    if attributes and attributes.source_db_url:
        org_secret = upsert_organization_secret(
            session=session,
            organization_id=organization_id,
            key=f"{source_data_create.id}_db_url",
            secret=attributes.source_db_url,
        )

    source_attributes = db.SourceAttributes(
        source_id=source_data_create.id,
        access_token=attributes.access_token,
        path=attributes.path,
        list_of_files_from_local_folder=attributes.list_of_files_from_local_folder,
        folder_id=attributes.folder_id,
        source_db_url=org_secret.id,
        source_table_name=attributes.source_table_name,
        id_column_name=attributes.id_column_name,
        text_column_names=attributes.text_column_names,
        source_schema_name=attributes.source_schema_name,
        chunk_size=attributes.chunk_size,
        chunk_overlap=attributes.chunk_overlap,
        metadata_column_names=attributes.metadata_column_names,
        timestamp_column_name=attributes.timestamp_column_name,
        url_column_name=attributes.url_column_name,
        update_existing=attributes.update_existing,
        query_filter=attributes.query_filter,
        timestamp_filter=attributes.timestamp_filter,
    )

    session.add(source_attributes)
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
    attributes: Optional[dict] = None,
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
        existing_source.attributes = attributes
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


def get_source_attributes(
    session_sql_alchemy: Session,
    organization_id: UUID,
    source_id: UUID,
) -> dict():
    """Get source attributes including decrypted database URL from the SourceAttributes table."""

    source_attributes = (
        session_sql_alchemy.query(db.SourceAttributes).filter(db.SourceAttributes.source_id == source_id).first()
    )

    attributes = SourceAttributes(
        access_token=source_attributes.access_token,
        path=source_attributes.path,
        list_of_files_from_local_folder=source_attributes.list_of_files_from_local_folder,
        folder_id=source_attributes.folder_id,
        source_table_name=source_attributes.source_table_name,
        id_column_name=source_attributes.id_column_name,
        text_column_names=source_attributes.text_column_names,
        source_schema_name=source_attributes.source_schema_name,
        chunk_size=source_attributes.chunk_size,
        chunk_overlap=source_attributes.chunk_overlap,
        metadata_column_names=source_attributes.metadata_column_names,
        timestamp_column_name=source_attributes.timestamp_column_name,
        url_column_name=source_attributes.url_column_name,
        update_existing=source_attributes.update_existing,
        query_filter=source_attributes.query_filter,
        timestamp_filter=source_attributes.timestamp_filter,
    )

    if source_attributes.source_db_url:
        db_url_secret = (
            session_sql_alchemy.query(db.OrganizationSecret)
            .filter(
                db.OrganizationSecret.id == source_attributes.source_db_url,
                db.OrganizationSecret.organization_id == organization_id,
            )
            .first()
        )
        if db_url_secret:
            attributes.source_db_url = db_url_secret.get_secret()

    return attributes.model_dump()
