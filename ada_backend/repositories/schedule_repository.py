"""
Repository for scheduled_workflows table operations.
Provides data access layer for scheduled workflow management.
"""

import logging
from typing import List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.database.models import ScheduledWorkflow, ScheduledWorkflowType

LOGGER = logging.getLogger(__name__)


def create_scheduled_workflow(session: Session, scheduled_workflow: ScheduledWorkflow) -> ScheduledWorkflow:
    """
    Create a new scheduled workflow record.

    Args:
        session: Database session
        scheduled_workflow: ScheduledWorkflow instance to create

    Returns:
        Created ScheduledWorkflow instance with ID and timestamps
    """
    session.add(scheduled_workflow)
    session.commit()
    session.refresh(scheduled_workflow)

    LOGGER.info(f"Created scheduled_workflow with ID: {scheduled_workflow.id}, UUID: {scheduled_workflow.uuid}")

    return scheduled_workflow


def get_scheduled_workflow_by_id(session: Session, workflow_id: int) -> ScheduledWorkflow:
    """
    Get a scheduled workflow by ID.

    Args:
        session: Database session
        workflow_id: Scheduled workflow ID

    Returns:
        ScheduledWorkflow instance

    Raises:
        ValueError: If workflow not found
    """
    workflow = session.query(ScheduledWorkflow).filter(ScheduledWorkflow.id == workflow_id).first()

    if not workflow:
        raise ValueError(f"Scheduled workflow with id {workflow_id} not found")

    return workflow


def get_scheduled_workflow_by_uuid(session: Session, workflow_uuid: UUID) -> ScheduledWorkflow:
    """
    Get a scheduled workflow by UUID.

    Args:
        session: Database session
        workflow_uuid: Scheduled workflow UUID

    Returns:
        ScheduledWorkflow instance

    Raises:
        ValueError: If workflow not found
    """
    workflow = session.query(ScheduledWorkflow).filter(ScheduledWorkflow.uuid == workflow_uuid).first()

    if not workflow:
        raise ValueError(f"Scheduled workflow with uuid {workflow_uuid} not found")

    return workflow


def update_scheduled_workflow(session: Session, scheduled_workflow: ScheduledWorkflow) -> ScheduledWorkflow:
    """
    Update a scheduled workflow record.

    Args:
        session: Database session
        scheduled_workflow: ScheduledWorkflow instance to update

    Returns:
        Updated ScheduledWorkflow instance
    """
    session.commit()
    session.refresh(scheduled_workflow)

    LOGGER.info(f"Updated scheduled_workflow with ID: {scheduled_workflow.id}")

    return scheduled_workflow


def delete_scheduled_workflow(session: Session, workflow_id: int) -> None:
    """
    Delete a scheduled workflow record.

    Args:
        session: Database session
        workflow_id: Scheduled workflow ID

    Raises:
        ValueError: If workflow not found
    """
    scheduled_workflow = get_scheduled_workflow_by_id(session, workflow_id)

    session.delete(scheduled_workflow)
    session.commit()

    LOGGER.info(f"Deleted scheduled_workflow with ID: {workflow_id}")


def list_scheduled_workflows(
    session: Session,
    organization_id: Optional[UUID] = None,
    project_id: Optional[UUID] = None,
    type: Optional[ScheduledWorkflowType] = None,
    enabled: Optional[bool] = None,
) -> List[ScheduledWorkflow]:
    """
    List scheduled workflows with optional filters.

    Args:
        session: Database session
        organization_id: Filter by organization
        project_id: Filter by project
        type: Filter by workflow type
        enabled: Filter by enabled status

    Returns:
        List of ScheduledWorkflow instances
    """
    query = session.query(ScheduledWorkflow)

    # Apply filters
    if organization_id:
        query = query.filter(ScheduledWorkflow.organization_id == organization_id)

    if project_id:
        query = query.filter(ScheduledWorkflow.project_id == project_id)

    if type:
        query = query.filter(ScheduledWorkflow.type == type)

    if enabled is not None:
        query = query.filter(ScheduledWorkflow.enabled == enabled)

    return query.all()


def get_scheduled_workflows_by_project(session: Session, project_id: UUID) -> List[ScheduledWorkflow]:
    """
    Get all scheduled workflows for a project.

    Args:
        session: Database session
        project_id: Project UUID

    Returns:
        List of ScheduledWorkflow instances
    """
    return list_scheduled_workflows(session, project_id=project_id)


def get_enabled_scheduled_workflows(session: Session) -> List[ScheduledWorkflow]:
    """
    Get all enabled scheduled workflows.

    Args:
        session: Database session

    Returns:
        List of enabled ScheduledWorkflow instances
    """
    return list_scheduled_workflows(session, enabled=True)
