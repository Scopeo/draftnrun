from uuid import UUID
from typing import Optional

import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ada_backend.database import models as db

LOGGER = logging.getLogger(__name__)


async def get_ingestion_task(
    session: AsyncSession,
    organization_id: UUID,
    task_id: Optional[UUID] = None,
) -> list[db.IngestionTask]:
    """Get ingestion tasks for a specific organization asynchronously."""
    stmt = select(db.IngestionTask).where(db.IngestionTask.organization_id == organization_id)

    if task_id:
        stmt = stmt.where(db.IngestionTask.id == task_id)

    result = await session.execute(stmt)
    tasks = result.scalars().all()
    return tasks


async def create_ingestion_task(
    session: AsyncSession,
    organization_id: UUID,
    source_name: str,
    source_type: db.SourceType,
    status: db.TaskStatus,
) -> UUID:
    """Create a new ingestion task for an organization asynchronously."""
    ingestion_task = db.IngestionTask(
        organization_id=organization_id,
        source_name=source_name,
        source_type=source_type,
        status=status,
    )
    session.add(ingestion_task)
    await session.commit()

    return ingestion_task.id


async def update_ingestion_task(
    session: AsyncSession,
    organization_id: UUID,
    source_id: UUID,
    source_name: str,
    source_type: db.SourceType,
    status: db.TaskStatus,
    task_id: UUID,
) -> None:
    """Update an ingestion task for an organization asynchronously."""
    try:
        stmt = select(db.IngestionTask).where(
            db.IngestionTask.organization_id == organization_id,
            db.IngestionTask.id == task_id,
        )
        existing_task = (await session.execute(stmt)).scalar_one_or_none()

        if existing_task:
            # Update existing task
            if source_id is not None:
                existing_task.source_id = source_id
            if source_name:
                existing_task.source_name = source_name
            if source_type:
                existing_task.source_type = source_type
            if status:
                existing_task.status = status

        await session.commit()
    except Exception as e:
        LOGGER.error(f"Error in upsert_ingestion_task: {str(e)}")
        await session.rollback()
        raise


async def delete_ingestion_task(
    session: AsyncSession,
    organization_id: UUID,
    id: UUID,
) -> None:
    """Delete an ingestion task asynchronously."""
    LOGGER.info(f"Deleting ingestion task with id {id} for organization id {organization_id}")

    stmt = select(db.IngestionTask).where(
        db.IngestionTask.organization_id == organization_id, db.IngestionTask.id == id
    )
    task_to_delete = (await session.execute(stmt)).scalar_one_or_none()

    if task_to_delete:
        await session.delete(task_to_delete)
        await session.commit()