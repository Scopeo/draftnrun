import logging
import uuid
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session

from ada_backend.database import models as db
from ada_backend.repositories.organization_repository import (
    upsert_organization_secret,
)
from ada_backend.schemas.ingestion_task_schema import SourceAttributes

LOGGER = logging.getLogger(__name__)


def _build_source_attribute_entries(source_id: UUID, attributes: dict[str, Any]) -> list[db.SourceAttribute]:
    return [
        db.SourceAttribute(
            source_id=source_id,
            attribute_name=attribute_name,
            value=value,
        )
        for attribute_name, value in attributes.items()
    ]


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

        eav_attributes = {
            key: value
            for key, value in attributes.model_dump(mode="json", exclude_none=True).items()
            if key in db.SourceAttributeKey.values()
        }
        eav_attributes["source_db_url"] = str(org_secret.id)

        source_attribute_entries = _build_source_attribute_entries(source_data_create.id, eav_attributes)

        session.add_all(source_attribute_entries)
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

    rows = session_sql_alchemy.query(db.SourceAttribute).filter(db.SourceAttribute.source_id == source_id).all()

    if not rows:
        raise ValueError(f"Source attributes not found for source_id={source_id}")

    attr_dict = {row.attribute_name: row.value for row in rows}

    source_db_url_key = db.SourceAttributeKey.SOURCE_DB_URL.value
    if source_db_url_key in attr_dict:
        secret_id = UUID(attr_dict[source_db_url_key])
        org_secret = (
            session_sql_alchemy.query(db.OrganizationSecret)
            .filter(
                db.OrganizationSecret.id == secret_id,
                db.OrganizationSecret.organization_id == organization_id,
            )
            .first()
        )
        attr_dict[source_db_url_key] = org_secret.get_secret() if org_secret else None

    return SourceAttributes(**attr_dict)


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
