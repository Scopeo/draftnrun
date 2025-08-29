from uuid import UUID
from typing import Optional
import logging

from sqlalchemy.orm import Session

from ada_backend.database import models as db

from ada_backend.repositories.organization_repository import (
    get_organization_secrets,
    upsert_organization_secret,
)

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
    attributes: Optional[dict] = None,
    secret_key: Optional[str] = None,
    secret: Optional[str] = None,
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
        attributes=attributes,
    )

    session.add(source_data_create)
    session.commit()
    session.refresh(source_data_create)

    if secret_key and secret:
        unique_key = f"{source_data_create.id}_{secret_key}"
        upsert_organization_secret(
            session=session,
            organization_id=organization_id,
            key=unique_key,
            secret=secret,
            secret_type=db.OrgSecretType.DATABASE_URL,
        )

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
) -> dict:
    """"""
    organization_secrets = get_organization_secrets(session_sql_alchemy, organization_id)

    source_secrets = [
        secret
        for secret in organization_secrets
        if (
            secret.secret_type == db.OrgSecretType.DATABASE_URL
            and secret.key
            and secret.key.startswith(f"{source_id}_")
        )
    ]

    data_source = (
        session_sql_alchemy.query(db.DataSource)
        .filter(db.DataSource.organization_id == organization_id, db.DataSource.id == source_id)
        .first()
    )

    if not data_source:
        raise ValueError(f"Data source with id {source_id} not found")

    attributes = data_source.attributes or {}
    for secret in source_secrets:
        if secret.key and secret.secret is not None:
            original_key = secret.key.replace(f"{source_id}_", "", 1)
            attributes[original_key] = secret.secret
    return attributes
