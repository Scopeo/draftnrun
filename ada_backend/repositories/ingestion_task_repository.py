import logging
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.database import models as db

LOGGER = logging.getLogger(__name__)


def get_ingestion_task(
    session: Session,
    organization_id: UUID,
    task_id: Optional[UUID] = None,
) -> list[db.IngestionTask]:
    """Get ingestion tasks for a specific organization."""
    query = session.query(db.IngestionTask).filter(db.IngestionTask.organization_id == organization_id)

    if task_id:
        query = query.filter(db.IngestionTask.id == task_id)

    tasks = query.all()
    return tasks


def create_ingestion_task(
    session: Session,
    organization_id: UUID,
    source_name: str,
    source_type: db.SourceType,
    status: db.TaskStatus,
    source_id: Optional[UUID] = None,
) -> UUID:
    """Create a new ingestion task for an organization."""
    ingestion_task = db.IngestionTask(
        organization_id=organization_id,
        source_name=source_name,
        source_type=source_type,
        status=status,
        source_id=source_id,
    )
    session.add(ingestion_task)
    session.commit()

    return ingestion_task.id


def update_ingestion_task(
    session: Session,
    organization_id: UUID,
    source_id: UUID,
    source_name: str,
    source_type: db.SourceType,
    status: db.TaskStatus,
    task_id: UUID,
    result_metadata: dict = None,
) -> None:
    """Update an ingestion task for an organization."""
    try:
        existing_task = (
            session.query(db.IngestionTask)
            .filter(
                db.IngestionTask.organization_id == organization_id,
                db.IngestionTask.id == task_id,
            )
            .first()
        )
        if existing_task:
            # Update existing task
            if source_id is not None:  # Only update if source_id is not None
                existing_task.source_id = source_id
            if source_name:
                existing_task.source_name = source_name
            if source_type:
                existing_task.source_type = source_type
            if status:
                existing_task.status = status
            if result_metadata is not None:
                existing_task.result_metadata = result_metadata

        session.commit()
    except Exception as e:
        LOGGER.error(f"Error in upsert_ingestion_task: {str(e)}")
        session.rollback()
        raise


def delete_ingestion_task(
    session: Session,
    organization_id: UUID,
    id: UUID,
) -> None:
    LOGGER.info(f"Deleting ingestion task with id {id} for organization id {organization_id}")
    session.query(db.IngestionTask).filter(
        db.IngestionTask.organization_id == organization_id, db.IngestionTask.id == id
    ).delete()
    session.commit()
