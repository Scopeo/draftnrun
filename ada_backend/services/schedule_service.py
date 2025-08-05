"""
Schedule service for managing scheduled workflows.
Provides business logic for creating, updating, and deleting scheduled workflows.
Uses repository pattern for data access and django sync for execution engine integration.
"""

import logging
from typing import List, Optional, Dict, Any
from uuid import UUID
import json

from sqlalchemy.orm import Session

from ada_backend.database.models import ScheduledWorkflowType, ScheduledWorkflow
from ada_backend.repositories.schedule_repository import (
    create_scheduled_workflow,
    get_scheduled_workflow_by_id,
    update_scheduled_workflow,
    delete_scheduled_workflow,
    get_scheduled_workflows_by_project,
)
from ada_backend.django_scheduler.sync_backend_to_django import sync_to_django
from ada_backend.schemas.schedule_base_schema import (
    ScheduleCreateSchema,
    ScheduleUpdateSchema,
    ScheduleResponse,
    ScheduleDeleteResponse,
)
from ada_backend.schemas.cron_schema import CronComponentConfig
from ada_backend.schemas.deployment_scheduling_schema import (
    DeploymentSchedulingError,
    DeploymentSchedulingResponse,
)
from ada_backend.database.models import Project
from ada_backend.services.cron_api_key_service import (
    cleanup_cron_api_keys_for_project,
    update_cron_api_key_for_project,
)

LOGGER = logging.getLogger(__name__)

# System user ID for automated operations
SYSTEM_USER_ID = UUID("00000000-0000-0000-0000-000000000000")


def scan_cron_components(session: Session, graph_runner_id: UUID) -> List[CronComponentConfig]:
    """
    Scan for cron components in a graph runner and extract their configuration.

    Args:
        session: Database session
        graph_runner_id: Graph runner UUID

    Returns:
        List of cron component configurations with:
        - component_instance_id: UUID of the component instance
        - cron_expression: Cron expression string
        - timezone: Timezone string
        - enabled: Boolean indicating if cron is enabled
    """
    from ada_backend.services.agent_runner_service import find_cron_scheduler_components, get_component_params

    try:
        # Find all cron scheduler components in the graph runner
        cron_components = find_cron_scheduler_components(session, graph_runner_id)

        cron_configs = []
        for component in cron_components:
            # Get component parameters
            params = get_component_params(session, component.id)

            # Extract cron configuration
            cron_config = {
                "component_instance_id": component.id,
                "cron_expression": params.get("cron_expression", "0 9 * * *"),  # Default: daily at 9 AM
                "timezone": params.get("timezone", "UTC"),
                "enabled": params.get("enabled", True),
            }

            cron_configs.append(CronComponentConfig(**cron_config))
            LOGGER.info(
                f"Found cron component {component.id}: {cron_config['cron_expression']} {cron_config['timezone']} enabled={cron_config['enabled']}"
            )

        LOGGER.info(f"Scanned {len(cron_configs)} cron components in graph runner {graph_runner_id}")
        return cron_configs

    except Exception as e:
        LOGGER.error(f"Failed to scan cron components: {str(e)}", exc_info=True)
        raise ValueError(f"Failed to scan cron components: {str(e)}") from e


def create_schedule(session: Session, schedule_data: ScheduleCreateSchema) -> ScheduleResponse:
    """
    Create a new scheduled workflow with business logic validation.

    Args:
        session: Database session
        schedule_data: Schedule creation data

    Returns:
        Created schedule response

    Raises:
        ValueError: If validation fails or sync fails
    """
    try:
        # Business logic validation
        if schedule_data.type == ScheduledWorkflowType.PROJECT and schedule_data.project_id is None:
            raise ValueError("project_id is required for Project type workflows")

        if schedule_data.type == ScheduledWorkflowType.INGESTION and schedule_data.project_id is not None:
            raise ValueError("project_id should be None for Ingestion type workflows")

        # Create the ScheduledWorkflow instance
        scheduled_workflow = ScheduledWorkflow(
            organization_id=schedule_data.organization_id,
            type=schedule_data.type,
            cron_expression=schedule_data.cron_expression,
            timezone=schedule_data.timezone,
            enabled=schedule_data.enabled,
            project_id=schedule_data.project_id,
            args=json.dumps(schedule_data.args) if schedule_data.args else "{}",
        )

        # Create the scheduled workflow using repository
        created_workflow = create_scheduled_workflow(session, scheduled_workflow)

        # Sync to django-celery-beat if enabled
        if schedule_data.enabled:
            try:
                sync_to_django(session, created_workflow.id)
            except Exception as e:
                LOGGER.error(f"Created scheduled_workflow but sync failed: {str(e)}")
                raise ValueError(f"Schedule created but sync to django-celery-beat failed: {str(e)}") from e

        return ScheduleResponse(
            id=created_workflow.id,
            uuid=created_workflow.uuid,
            organization_id=created_workflow.organization_id,
            project_id=created_workflow.project_id,
            type=created_workflow.type,
            cron_expression=created_workflow.cron_expression,
            timezone=created_workflow.timezone,
            enabled=created_workflow.enabled,
            args=created_workflow.args,
            created_at=str(created_workflow.created_at),
            updated_at=str(created_workflow.updated_at),
        )

    except Exception as e:
        LOGGER.error(f"Failed to create schedule: {str(e)}", exc_info=True)
        raise


def update_schedule(session: Session, workflow_id: int, updates: ScheduleUpdateSchema) -> ScheduleResponse:
    """
    Update a scheduled workflow with business logic validation.

    Args:
        session: Database session
        workflow_id: Scheduled workflow ID
        updates: Schedule update data

    Returns:
        Updated schedule response

    Raises:
        ValueError: If workflow not found or sync fails
    """
    try:
        # Get current workflow to validate business rules
        current_workflow = get_scheduled_workflow_by_id(session, workflow_id)

        # Business logic validation for updates
        if updates.cron_expression is not None and not updates.cron_expression.strip():
            raise ValueError("cron_expression cannot be empty")

        if updates.timezone is not None and not updates.timezone.strip():
            raise ValueError("timezone cannot be empty")

        # Validate project_id rules if being updated
        if updates.type is not None:
            # Always validate project_id based on the type being set
            if updates.type == ScheduledWorkflowType.PROJECT and updates.project_id is None:
                raise ValueError("project_id is required for Project type workflows")

        # Update fields on the current workflow instance
        update_dict = {k: v for k, v in updates.dict().items() if v is not None}

        for field, value in update_dict.items():
            if hasattr(current_workflow, field):
                if field == "args" and isinstance(value, dict):
                    setattr(current_workflow, field, json.dumps(value))
                else:
                    setattr(current_workflow, field, value)

        # Update the scheduled workflow using repository
        updated_workflow = update_scheduled_workflow(session, current_workflow)

        # Sync to django-celery-beat
        try:
            sync_to_django(session, workflow_id)
        except Exception as e:
            LOGGER.error(f"Updated scheduled_workflow but sync failed: {str(e)}")
            raise ValueError(f"Schedule updated but sync to django-celery-beat failed: {str(e)}") from e

        return ScheduleResponse(
            id=updated_workflow.id,
            uuid=updated_workflow.uuid,
            organization_id=updated_workflow.organization_id,
            project_id=updated_workflow.project_id,
            type=updated_workflow.type,
            cron_expression=updated_workflow.cron_expression,
            timezone=updated_workflow.timezone,
            enabled=updated_workflow.enabled,
            args=updated_workflow.args,
            created_at=str(updated_workflow.created_at),
            updated_at=str(updated_workflow.updated_at),
        )

    except Exception as e:
        LOGGER.error(f"Failed to update schedule: {str(e)}", exc_info=True)
        raise


def delete_schedule(session: Session, workflow_id: int) -> ScheduleDeleteResponse:
    """
    Delete a scheduled workflow.
    Note: The corresponding django-celery-beat task will be automatically deleted
    due to the ON DELETE CASCADE foreign key constraint.

    Args:
        session: Database session
        workflow_id: Scheduled workflow ID

    Returns:
        Deletion response

    Raises:
        ValueError: If workflow not found
    """
    try:
        # Delete the scheduled workflow using repository
        delete_scheduled_workflow(session, workflow_id)

        # Note: django-celery-beat task is automatically deleted via CASCADE

        return ScheduleDeleteResponse(schedule_id=workflow_id, message="Schedule deleted successfully")

    except Exception as e:
        LOGGER.error(f"Failed to delete schedule: {str(e)}", exc_info=True)
        raise


def get_project_schedules(session: Session, project_id: UUID) -> List[ScheduleResponse]:
    """
    Get all scheduled workflows for a project.

    Args:
        session: Database session
        project_id: Project UUID

    Returns:
        List of schedules response
    """
    try:
        workflows = get_scheduled_workflows_by_project(session, project_id)

        schedule_responses = [
            ScheduleResponse(
                id=workflow.id,
                uuid=workflow.uuid,
                organization_id=workflow.organization_id,
                project_id=workflow.project_id,
                type=workflow.type,
                cron_expression=workflow.cron_expression,
                timezone=workflow.timezone,
                enabled=workflow.enabled,
                args=workflow.args,
                created_at=str(workflow.created_at),
                updated_at=str(workflow.updated_at),
            )
            for workflow in workflows
        ]

        return schedule_responses

    except Exception as e:
        LOGGER.error(f"Failed to get project schedules: {str(e)}", exc_info=True)
        raise


def cleanup_schedules_for_project(session: Session, project_id: UUID, cleanup_api_key: bool = False) -> Dict[str, Any]:
    """
    Delete all scheduled workflows associated with a project.
    This is typically called when a project is deleted.

    Args:
        session: Database session
        project_id: Project UUID
        cleanup_api_key: Whether to also cleanup API keys (not implemented here)

    Returns:
        Dictionary with status and cleanup results
    """
    try:
        # Get all schedules for the project
        schedules_to_delete = get_project_schedules(session, project_id)

        deleted_count = 0
        errors = []

        for schedule in schedules_to_delete:
            try:
                delete_schedule(session, schedule.id)
                deleted_count += 1
                LOGGER.info(f"Deleted schedule {schedule.id} for project {project_id}")
            except Exception as e:
                error_msg = f"Failed to delete schedule {schedule.id} for project {project_id}: {str(e)}"
                LOGGER.error(error_msg)
                errors.append(error_msg)

        result = {
            "status": "SUCCESS",
            "deleted_count": deleted_count,
            "errors": errors,
            "message": f"Successfully deleted {deleted_count} schedules for project {project_id}",
        }

        LOGGER.info(f"Cleanup of schedules for project {project_id}: {deleted_count} deleted, {len(errors)} errors")
        return result

    except Exception as e:
        error_msg = f"Failed to cleanup schedules for project {project_id}: {str(e)}"
        LOGGER.error(error_msg, exc_info=True)
        return {"status": "FAILED", "error": error_msg, "deleted_count": 0, "errors": [error_msg]}


def handle_scheduling_on_deployment(
    session: Session, graph_runner_id: UUID, project_id: UUID, previous_production_graph_id: Optional[UUID] = None
) -> DeploymentSchedulingResponse:
    """
    Handle scheduling logic when a graph runner is deployed to production.

    Scans for cron components in the graph and:
    - Creates or updates scheduled workflows for enabled cron components
    - Deletes scheduled workflows for disabled cron components

    Args:
        session: Database session
        graph_runner_id: ID of the graph runner being deployed to production
        project_id: Project ID
        previous_production_graph_id: ID of the previous production graph runner (if any)

    Returns:
        DeploymentSchedulingResponse with scheduling results
    """
    print(f"=== SCHEDULING DEBUG START ===")
    print(f"Handling scheduling for graph_runner_id: {graph_runner_id}")
    print(f"Project_id: {project_id}")

    try:
        print("1. Scanning for cron components...")
        cron_configs = scan_cron_components(session, graph_runner_id)
        print(f"Found {len(cron_configs)} cron components")

        schedules_updated = 0
        schedules_removed = 0
        schedules_errors = []

        print("2. Getting existing schedules...")
        existing_schedules = get_project_schedules(session, project_id)
        print(f"Found {len(existing_schedules)} existing schedules")

        # Handle each cron component configuration
        for i, cron_config in enumerate(cron_configs):
            print(f"3.{i+1}. Processing cron component {cron_config.component_instance_id}...")
            try:
                # Find existing schedule for this cron component
                existing_schedule = None
                for schedule in existing_schedules:
                    try:
                        schedule_args = json.loads(schedule.args) if schedule.args else {}
                        if schedule_args.get("component_instance_id") == str(cron_config.component_instance_id):
                            existing_schedule = schedule
                            break
                    except (json.JSONDecodeError, KeyError):
                        continue

                if existing_schedule:
                    print(f"   Found existing schedule: {existing_schedule.id}")
                else:
                    print(f"   No existing schedule found")

                if cron_config.enabled:
                    print(f"   Cron is enabled, processing...")
                    # Cron is enabled - create or update schedule
                    if existing_schedule:
                        print(f"   Updating existing schedule...")
                        updates = ScheduleUpdateSchema(
                            cron_expression=cron_config.cron_expression,
                            timezone=cron_config.timezone,
                            enabled=cron_config.enabled,
                            args={
                                "component_instance_id": str(cron_config.component_instance_id),
                                "cron_expression": cron_config.cron_expression,
                                "timezone": cron_config.timezone,
                            },
                        )
                        result = update_schedule(session=session, workflow_id=existing_schedule.id, updates=updates)
                        if result:  # Only count if schedule was actually updated
                            schedules_updated += 1
                            print(f"   ✅ Updated schedule for cron component {cron_config.component_instance_id}")
                    else:
                        print(f"   Creating new schedule...")
                        # Cron is enabled - create the schedule
                        organization_id = (
                            session.query(Project).filter(Project.id == project_id).first().organization_id
                        )

                        schedule_data = ScheduleCreateSchema(
                            organization_id=organization_id,
                            type=ScheduledWorkflowType.PROJECT,
                            cron_expression=cron_config.cron_expression,
                            timezone=cron_config.timezone,
                            enabled=cron_config.enabled,
                            project_id=project_id,
                            args={
                                "component_instance_id": str(cron_config.component_instance_id),
                                "cron_expression": cron_config.cron_expression,
                                "timezone": cron_config.timezone,
                            },
                        )

                        result = create_schedule(session=session, schedule_data=schedule_data)
                        if result:  # Only count if schedule was actually created
                            schedules_updated += 1
                            print(f"   ✅ Created new schedule for cron component {cron_config.component_instance_id}")

                else:
                    print(f"   Cron is disabled, deleting schedule if exists...")
                    # Cron is disabled - delete associated schedule if exists
                    if existing_schedule:
                        delete_schedule(session=session, workflow_id=existing_schedule.id)
                        schedules_removed += 1
                        print(
                            f"   ✅ Deleted disabled schedule for cron component {cron_config.component_instance_id}"
                        )

            except Exception as e:
                error_msg = f"Failed to handle cron component {cron_config.component_instance_id}: {str(e)}"
                print(f"   ❌ Error: {error_msg}")
                LOGGER.error(error_msg)
                schedules_errors.append(
                    DeploymentSchedulingError(component_instance_id=cron_config.component_instance_id, error=error_msg)
                )

        # Check if any cron components are enabled
        enabled_cron_components = [config for config in cron_configs if config.enabled]

        if not enabled_cron_components:
            print("3. No enabled cron components found - deleting all existing schedules...")
            for schedule in existing_schedules:
                try:
                    print(f"   Deleting schedule {schedule.id} - no enabled cron components")
                    delete_schedule(session=session, workflow_id=schedule.id)
                    schedules_removed += 1
                    print(f"   ✅ Deleted schedule {schedule.id}")
                except Exception as e:
                    error_msg = f"Failed to delete schedule {schedule.id}: {str(e)}"
                    print(f"   ❌ Error: {error_msg}")
                    LOGGER.error(error_msg)
                    schedules_errors.append(DeploymentSchedulingError(schedule_id=schedule.id, error=error_msg))

            # Clean up API key when all schedules are removed
            if existing_schedules:
                print("   Cleaning up API key - all schedules removed...")
                try:
                    cleanup_result = cleanup_cron_api_keys_for_project(
                        session=session, project_id=project_id, revoker_user_id=SYSTEM_USER_ID
                    )
                    if cleanup_result["status"] == "SUCCESS":
                        print(f"   ✅ Cleaned up API key for project {project_id}")
                    else:
                        print(f"   ❌ Failed to cleanup API key: {cleanup_result.get('error', 'Unknown error')}")
                except Exception as e:
                    print(f"   ❌ Exception during API key cleanup: {str(e)}")
                    LOGGER.error(f"Exception during API key cleanup for project {project_id}: {str(e)}", exc_info=True)

        print("4. Processing API key management...")
        # Generate/rotate API key if schedules were created or updated
        if schedules_updated > 0:
            print(f"   Schedules updated ({schedules_updated}), generating API key...")
            try:
                api_key_result = update_cron_api_key_for_project(
                    session=session, project_id=project_id, creator_user_id=SYSTEM_USER_ID
                )
                if api_key_result["status"] == "SUCCESS":
                    print(f"   ✅ Generated/rotated API key for project {project_id}")
                else:
                    print(f"   ❌ Failed to generate API key: {api_key_result.get('error', 'Unknown error')}")
            except Exception as e:
                print(f"   ❌ Exception during API key generation: {str(e)}")
                LOGGER.error(f"Exception during API key generation for project {project_id}: {str(e)}", exc_info=True)
        else:
            print(f"   No schedules updated, skipping API key generation")

        print("5. Creating response...")
        result = DeploymentSchedulingResponse(
            project_id=project_id,
            graph_runner_id=graph_runner_id,
            previous_production_graph_id=previous_production_graph_id,
            schedules_updated=schedules_updated,
            schedules_removed=schedules_removed,
            schedules_errors=schedules_errors,
            message="Scheduling handled successfully",
        )

        print(
            f"✅ Scheduling completed: {schedules_updated} updated, {schedules_removed} removed, {len(schedules_errors)} errors"
        )
        print(f"=== SCHEDULING DEBUG END ===")
        return result

    except Exception as e:
        error_msg = f"Failed to handle scheduling on deployment: {str(e)}"
        print(f"❌ Scheduling failed: {error_msg}")
        print(f"=== SCHEDULING DEBUG END WITH ERROR ===")
        LOGGER.error(error_msg, exc_info=True)
        return DeploymentSchedulingResponse(
            project_id=project_id,
            graph_runner_id=graph_runner_id,
            previous_production_graph_id=previous_production_graph_id,
            schedules_updated=0,
            schedules_removed=0,
            schedules_errors=[DeploymentSchedulingError(error=error_msg)],
            message="Scheduling failed",
        )
