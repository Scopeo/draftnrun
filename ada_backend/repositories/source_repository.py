from uuid import UUID
from typing import Optional
import logging
import uuid

from sqlalchemy.orm import Session
from sqlalchemy import func, and_, exists, select

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
    source_id: Optional[UUID] = None,
) -> UUID:
    if source_id is None:
        source_id = uuid.uuid4()

    existing_source = get_data_source_by_org_id(session, organization_id, source_id)
    if existing_source is not None:
        LOGGER.info(f"Source with id {source_id} already exists for organization {organization_id}, skipping creation")
        return existing_source.id

    source_data_create = db.DataSource(
        id=source_id,
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
            key=f"db_url__{source_data_create.id}",
            secret=attributes.source_db_url,
            secret_type=db.OrgSecretType.PASSWORD,
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
            url_pattern=attributes.url_pattern,
            update_existing=attributes.update_existing,
            query_filter=attributes.query_filter,
            timestamp_filter=attributes.timestamp_filter,
        )

        session.add(source_attributes)
        session.commit()
    return source_data_create.id


def update_source_last_edited_time(
    session_sql_alchemy: Session,
    organization_id: UUID,
    source_id: UUID,
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
        existing_source.updated_at = func.now()

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
) -> SourceAttributes:
    """Get source attributes including decrypted database URL from the SourceAttributes table."""

    result = (
        session_sql_alchemy.query(db.SourceAttributes, db.OrganizationSecret)
        .outerjoin(
            db.OrganizationSecret,
            and_(
                db.SourceAttributes.source_db_url == db.OrganizationSecret.id,
                db.OrganizationSecret.organization_id == organization_id,
            ),
        )
        .filter(db.SourceAttributes.source_id == source_id)
        .first()
    )

    if not result:
        raise ValueError(f"Source attributes not found for source_id={source_id}")

    source_attributes, org_secret = result

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
        url_pattern=source_attributes.url_pattern,
        update_existing=source_attributes.update_existing,
        query_filter=source_attributes.query_filter,
        timestamp_filter=source_attributes.timestamp_filter,
    )

    if org_secret:
        attributes.source_db_url = org_secret.get_secret()

    return attributes


def get_projects_using_source(
    session: Session,
    organization_id: UUID,
    source_id: UUID,
) -> list[db.Project]:

    source_id_str = str(source_id)

    projects = (
        session.query(db.Project)
        .filter(db.Project.organization_id == organization_id)
        .filter(
            exists(
                select(1)
                .select_from(db.ProjectEnvironmentBinding)
                .join(db.GraphRunner, db.ProjectEnvironmentBinding.graph_runner_id == db.GraphRunner.id)
                .join(db.GraphRunnerNode, db.GraphRunnerNode.graph_runner_id == db.GraphRunner.id)
                .join(db.ComponentInstance, db.GraphRunnerNode.node_id == db.ComponentInstance.id)
                .join(db.BasicParameter, db.BasicParameter.component_instance_id == db.ComponentInstance.id)
                .join(
                    db.ComponentParameterDefinition,
                    db.BasicParameter.parameter_definition_id == db.ComponentParameterDefinition.id,
                )
                .where(db.ProjectEnvironmentBinding.project_id == db.Project.id)
                .where(db.ComponentParameterDefinition.type == db.ParameterType.DATA_SOURCE)
                .where(db.BasicParameter.value.isnot(None))
                # TODO: Refactor to move source_id to a dedicated DB field (or JSONB with a proper index)
                # to avoid this inefficient textual search.
                .where(db.BasicParameter.value.contains(f'"{source_id_str}"'))
            )
        )
        .all()
    )

    return projects
