"""
Celery tasks for executing scheduled workflows.
These tasks are triggered by Celery Beat on schedule and make HTTP calls to the production endpoint.
"""

import logging
import requests
from datetime import datetime
from uuid import UUID
from typing import Optional, Dict, Any
from datetime import timedelta

from celery import current_task
from sqlalchemy.exc import SQLAlchemyError

from ada_backend.database.models import ScheduledExecution, ScheduledWorkflow, TaskStatus
from ada_backend.celery_app import celery_app
from ada_backend.database.setup_db import get_db_session
from ada_backend.services.cron_api_key_service import get_existing_cron_api_key
from settings import settings

LOGGER = logging.getLogger(__name__)



def make_inference_request(
    project_id: str, 
    api_key: str, 
    input_data: Dict[str, Any],
    timeout: int = 600
) -> Dict[str, Any]:
    """
    Make HTTP request to the production inference endpoint.
    
    Args:
        project_id: Project UUID string
        api_key: Cron job API key for authentication
        input_data: Input data for the workflow
        timeout: Request timeout in seconds
        
    Returns:
        Response data from the inference endpoint
    """
    url = f"{settings.ADA_URL}/projects/{project_id}/production/run"
    headers = {
        "X-API-Key": api_key,
        "Content-Type": "application/json"
    }
    
    LOGGER.info(f"Making inference request to {url} for scheduled workflow")
    
    try:
        response = requests.post(
            url=url,
            headers=headers,
            json=input_data,
            timeout=timeout
        )
        
        response.raise_for_status()
        result = response.json()
        
        LOGGER.info(f"Successful inference request for project {project_id}")
        return {
            "status": "SUCCESS",
            "result": result,
            "status_code": response.status_code
        }
        
    except requests.exceptions.HTTPError as e:
        error_msg = f"HTTP error {e.response.status_code}: {e.response.text}"
        LOGGER.error(f"HTTP error in inference request: {error_msg}")
        return {
            "status": "HTTP_ERROR",
            "error": error_msg,
            "status_code": e.response.status_code
        }
    except requests.exceptions.Timeout:
        error_msg = f"Request timeout after {timeout} seconds"
        LOGGER.error(f"Timeout in inference request: {error_msg}")
        return {
            "status": "TIMEOUT_ERROR",
            "error": error_msg
        }
    except requests.exceptions.RequestException as e:
        error_msg = f"Request error: {str(e)}"
        LOGGER.error(f"Request error in inference request: {error_msg}", exc_info=True)
        return {
            "status": "REQUEST_ERROR",
            "error": error_msg
        }
    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        LOGGER.error(f"Unexpected error in inference request: {error_msg}", exc_info=True)
        return {
            "status": "UNEXPECTED_ERROR",
            "error": error_msg
        }


@celery_app.task(bind=True, name="execute_scheduled_workflow")
def execute_scheduled_workflow(self, project_id: str, graph_runner_id: str, schedule_id: Optional[str] = None):
    """
    Execute a scheduled workflow via HTTP call to production endpoint.
    Creates ScheduledExecution database record for tracking.
    
    Args:
        self: Bound task instance (from bind=True)
        project_id: UUID of the project to execute
        graph_runner_id: UUID of the graph runner to execute
        schedule_id: Optional schedule ID for tracking
        
    Returns:
        dict: Execution result with status and data
    """
    task_id = self.request.id
    start_time = datetime.now()
    execution_record = None

    LOGGER.info(
        f"Starting scheduled workflow execution: task_id={task_id}, project={project_id}, graph={graph_runner_id}"
    )

    try:
        # Get database session
        with get_db_session() as session:
            # Find the corresponding ScheduledWorkflow record
            scheduled_workflow = None
            if schedule_id:
                # Try to find by scheduler component ID first
                scheduled_workflow = session.query(ScheduledWorkflow).filter(
                    ScheduledWorkflow.project_id == UUID(project_id),
                    ScheduledWorkflow.graph_runner_id == UUID(graph_runner_id),
                    ScheduledWorkflow.cron_scheduler_component_id == UUID(schedule_id),
                    ScheduledWorkflow.is_active == True
                ).first()
            
            if not scheduled_workflow:
                # Fallback: find by project and graph runner
                scheduled_workflow = session.query(ScheduledWorkflow).filter(
                    ScheduledWorkflow.project_id == UUID(project_id),
                    ScheduledWorkflow.graph_runner_id == UUID(graph_runner_id),
                    ScheduledWorkflow.is_active == True
                ).first()
            
            if not scheduled_workflow:
                error_msg = f"No active ScheduledWorkflow found for project {project_id}, graph {graph_runner_id}"
                LOGGER.error(error_msg)
                return {
                    "status": "FAILED",
                    "error": error_msg,
                    "task_id": task_id,
                    "execution_time": (datetime.now() - start_time).total_seconds()
                }

            # Create ScheduledExecution record
            execution_record = ScheduledExecution(
                scheduled_workflow_id=scheduled_workflow.id,
                celery_task_id=task_id,
                status=TaskStatus.IN_PROGRESS,
                started_at=start_time
            )
            session.add(execution_record)
            session.commit()
            
            LOGGER.info(f"Created ScheduledExecution record {execution_record.id} for task {task_id}")

            # Get the cron API key for this project
            cron_api_key = get_existing_cron_api_key(session, UUID(project_id))
            
            if not cron_api_key:
                error_msg = f"No cron API key found for project {project_id}"
                LOGGER.error(error_msg)
                
                # Update execution record with failure
                execution_record.status = TaskStatus.FAILED
                execution_record.error_message = error_msg
                execution_record.completed_at = datetime.now()
                session.commit()
                
                return {
                    "status": "FAILED",
                    "error": error_msg,
                    "task_id": task_id,
                    "execution_time": (datetime.now() - start_time).total_seconds(),
                    "execution_record_id": str(execution_record.id)
                }
            
            if not cron_api_key.is_active:
                error_msg = f"Cron API key for project {project_id} is not active"
                LOGGER.error(error_msg)
                
                # Update execution record with failure
                execution_record.status = TaskStatus.FAILED
                execution_record.error_message = error_msg
                execution_record.completed_at = datetime.now()
                session.commit()
                
                return {
                    "status": "FAILED", 
                    "error": error_msg,
                    "task_id": task_id,
                    "execution_time": (datetime.now() - start_time).total_seconds(),
                    "execution_record_id": str(execution_record.id)
                }

            raw_api_key = cron_api_key.get_raw_key()
            if not raw_api_key:
                error_msg = f"No raw API key stored for cron job in project {project_id}"
                LOGGER.error(error_msg)
                
                # Update execution record with failure
                execution_record.status = TaskStatus.FAILED
                execution_record.error_message = error_msg
                execution_record.completed_at = datetime.now()
                session.commit()
                
                return {
                    "status": "FAILED",
                    "error": error_msg,
                    "task_id": task_id,
                    "execution_time": (datetime.now() - start_time).total_seconds(),
                    "execution_record_id": str(execution_record.id)
                }

        input_data = {
            "messages": [
                {
                    "role": "system",
                    "content": f"Scheduled execution triggered at {start_time.isoformat()}"
                }
            ],
            "scheduled": True,
            "task_id": task_id,
            "schedule_id": schedule_id,
            "execution_timestamp": start_time.isoformat(),
            "execution_record_id": str(execution_record.id)
        }

        response = make_inference_request(
            project_id=project_id,
            api_key=raw_api_key, 
            input_data=input_data,
        )

        execution_time = (datetime.now() - start_time).total_seconds()
        completed_at = datetime.now()

        # Update execution record with results
        with get_db_session() as session:
            # Re-fetch the execution record in this new session
            execution_record = session.query(ScheduledExecution).filter(
                ScheduledExecution.id == execution_record.id
            ).first()
            
            if execution_record:
                execution_record.completed_at = completed_at
                
                if response["status"] == "SUCCESS":
                    execution_record.status = TaskStatus.COMPLETED
                    execution_record.execution_result = response["result"]
                    
                    LOGGER.info(
                        f"Successfully executed scheduled workflow: project={project_id}, "
                        f"task_id={task_id}, execution_time={execution_time:.2f}s"
                    )
                    
                    session.commit()
                    
                    return {
                        "status": "SUCCESS",
                        "project_id": project_id,
                        "graph_runner_id": graph_runner_id,
                        "task_id": task_id,
                        "execution_time": execution_time,
                        "result": response["result"],
                        "execution_record_id": str(execution_record.id)
                    }
                else:
                    execution_record.status = TaskStatus.FAILED
                    execution_record.error_message = response["error"]
                    
                    LOGGER.error(
                        f"Failed to execute scheduled workflow: project={project_id}, "
                        f"task_id={task_id}, error={response['error']}"
                    )
                    
                    session.commit()
                    
                    return {
                        "status": "FAILED",
                        "project_id": project_id,
                        "graph_runner_id": graph_runner_id,
                        "task_id": task_id,
                        "execution_time": execution_time,
                        "error": response["error"],
                        "execution_record_id": str(execution_record.id)
                    }

    except Exception as e:
        error_msg = f"Unexpected error in scheduled workflow execution: {str(e)}"
        LOGGER.error(error_msg, exc_info=True)
        
        # Update execution record with failure if it exists
        if execution_record:
            try:
                with get_db_session() as session:
                    # Re-fetch the execution record
                    execution_record = session.query(ScheduledExecution).filter(
                        ScheduledExecution.id == execution_record.id
                    ).first()
                    
                    if execution_record:
                        execution_record.status = TaskStatus.FAILED
                        execution_record.error_message = error_msg
                        execution_record.completed_at = datetime.now()
                        session.commit()
            except Exception as db_error:
                LOGGER.error(f"Failed to update execution record after error: {str(db_error)}", exc_info=True)
        
        return {
            "status": "FAILED",
            "error": error_msg,
            "task_id": task_id,
            "execution_time": (datetime.now() - start_time).total_seconds(),
            "execution_record_id": str(execution_record.id) if execution_record else None
        }


@celery_app.task(name="cleanup_old_executions")
def cleanup_old_executions(days_to_keep: int = 90) -> Dict[str, Any]:
    """
    Clean up old execution records from the database.
    
    Args:
        days_to_keep: Number of days to keep execution records
        
    Returns:
        dict: Cleanup result with statistics
    """
    
    cutoff_date = datetime.now() - timedelta(days=days_to_keep)
    
    LOGGER.info(f"Starting cleanup of execution records older than {days_to_keep} days (before {cutoff_date})")
    
    try:
        with get_db_session() as session:
            # Delete old execution records
            deleted_count = session.query(ScheduledExecution)\
                .filter(ScheduledExecution.created_at < cutoff_date)\
                .delete()
            
            session.commit()
            
            LOGGER.info(f"Successfully deleted {deleted_count} old execution records")
            
            return {
                "status": "SUCCESS",
                "deleted_records": deleted_count,
                "cutoff_date": cutoff_date.isoformat(),
                "days_to_keep": days_to_keep,
                "message": f"Cleaned up {deleted_count} execution records older than {days_to_keep} days"
            }
            
    except Exception as e:
        error_msg = f"Error during cleanup of old executions: {str(e)}"
        LOGGER.error(error_msg, exc_info=True)
        return {
            "status": "FAILED",
            "error": error_msg,
            "days_to_keep": days_to_keep
        }
