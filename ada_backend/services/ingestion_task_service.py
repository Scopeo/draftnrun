from uuid import UUID
from typing import List
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from ada_backend.repositories.ingestion_task_repository import (
    get_ingestion_task,
    create_ingestion_task,
    update_ingestion_task,
    delete_ingestion_task,
)
from ada_backend.schemas.ingestion_task_schema import (
    IngestionTaskQueue,
    IngestionTaskUpdate,
    IngestionTaskResponse,
)
from ada_backend.utils.redis_client import push_ingestion_task

LOGGER = logging.getLogger(__name__)


async def get_ingestion_task_by_organization_id(
    session: AsyncSession,
    organization_id: UUID,
) -> List[IngestionTaskResponse]:
    """Get all tasks for an organization through the service layer asynchronously."""
    try:
        tasks = await get_ingestion_task(session, organization_id)
        return [
            IngestionTaskResponse(
                id=task.id,
                source_id=task.source_id,
                source_name=task.source_name,
                source_type=task.source_type,
                status=task.status,
                created_at=str(task.created_at),
                updated_at=str(task.updated_at),
            )
            for task in tasks
        ]
    except Exception as e:
        LOGGER.error(f"Error in get_ingestion_task_by_organization: {str(e)}")
        raise ValueError(f"Failed to get tasks: {str(e)}")


async def create_ingestion_task_by_organization(
    session: AsyncSession,
    organization_id: UUID,
    ingestion_task_data: IngestionTaskQueue,
) -> UUID:
    """Create a new source for an organization asynchronously."""
    try:
        task_id = await create_ingestion_task(
            session,
            organization_id,
            ingestion_task_data.source_name,
            ingestion_task_data.source_type,
            ingestion_task_data.status,
        )

        LOGGER.info(f"Task created in database with ID {task_id}")

        ingestion_id = f"ing-{str(task_id)[:8]}"
        LOGGER.info(f"Sending task to Redis with ingestion_id: {ingestion_id}")

        # TODO: put in async the redis push
        redis_result = push_ingestion_task(
            ingestion_id=ingestion_id,
            source_name=ingestion_task_data.source_name,
            source_type=ingestion_task_data.source_type.value,
            organization_id=str(organization_id),
            task_id=str(task_id),
            source_attributes=ingestion_task_data.source_attributes,
        )

        if not redis_result:
            LOGGER.warning(f"Task {task_id} created in database but failed to push to Redis queue")
            from ada_backend.database import models as db
            from ada_backend.repositories.ingestion_task_repository import update_ingestion_task, get_ingestion_task

            tasks = await get_ingestion_task(session, organization_id, task_id=task_id)
            source_id = tasks[0].source_id if tasks else None

            await update_ingestion_task(
                session,
                organization_id,
                source_id,
                ingestion_task_data.source_name,
                ingestion_task_data.source_type,
                db.TaskStatus.FAILED,
                task_id,
            )
            LOGGER.info(f"Updated task {task_id} status to FAILED due to Redis push failure")
        else:
            LOGGER.info(f"Task {task_id} successfully pushed to Redis queue")

        return task_id
    except Exception as e:
        LOGGER.error(f"Error in create_ingestion_task_by_organization: {str(e)}", exc_info=True)
        raise ValueError(f"Failed to create task: {str(e)}")


async def upsert_ingestion_task_by_organization_id(
    session: AsyncSession,
    organization_id: UUID,
    ingestion_task_data: IngestionTaskUpdate,
) -> None:
    """Create a new source for an organization asynchronously."""
    try:
        return await update_ingestion_task(
            session,
            organization_id,
            ingestion_task_data.source_id,
            ingestion_task_data.source_name,
            ingestion_task_data.source_type,
            ingestion_task_data.status,
            ingestion_task_data.id,
        )
    except Exception as e:
        LOGGER.error(f"Error in upsert_ingestion_task_by_organization_id: {str(e)}")
        raise ValueError(f"Failed to upsert task: {str(e)}")


async def delete_ingestion_task_by_id(
    session: AsyncSession,
    organization_id: UUID,
    id: UUID,
) -> None:
    """Delete sources with matching name in the organization asynchronously."""
    try:
        await delete_ingestion_task(session, organization_id, id)
    except Exception as e:
        LOGGER.error(f"Error in delete_ingestion_task_by_id: {str(e)}")
        raise ValueError(f"Failed to delete task: {str(e)}")
