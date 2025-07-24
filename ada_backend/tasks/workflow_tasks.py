"""
Celery tasks for executing scheduled workflows.
These tasks are triggered by Celery Beat on schedule and make HTTP calls to the production endpoint.
Uses simplified django-celery-beat only approach - no redundant tables.
"""

import logging
import requests
import json
from datetime import datetime
from uuid import UUID
from typing import Optional, Dict, Any
from datetime import timedelta

from celery import current_task
from sqlalchemy.exc import SQLAlchemyError

from ada_backend.database.models import TaskStatus
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


def get_production_endpoint_url(project_id: str) -> str:
    """
    Build the production endpoint URL for a project.
    
    Args:
        project_id: Project UUID string
        
    Returns:
        Full URL for the production endpoint
    """
    return f"{settings.ADA_URL}/projects/{project_id}/production/run"


@celery_app.task(name="execute_scheduled_workflow", bind=True)
def execute_scheduled_workflow(
    self, 
    project_id: str, 
    graph_runner_id: str, 
    scheduler_id: str,
    **kwargs
):
    """
    Execute a scheduled workflow via HTTP call to production endpoint.
    This task is triggered by Celery Beat based on cron schedules.
    
    Args:
        project_id: Project UUID string
        graph_runner_id: Graph runner UUID string  
        scheduler_id: Scheduler component instance UUID string
        **kwargs: Additional arguments from periodic task (cron_expression, timezone, etc.)
        
    Returns:
        Execution result
    """
    task_id = self.request.id
    start_time = datetime.utcnow()
    
    # Extract additional info from kwargs
    cron_expression = kwargs.get("cron_expression", "unknown")
    timezone = kwargs.get("timezone", "UTC")
    user_timezone = kwargs.get("user_timezone", timezone)
    created_at = kwargs.get("created_at")
    
    LOGGER.info(f"Starting scheduled workflow execution: task={task_id}, project={project_id}, graph={graph_runner_id}")
    LOGGER.info(f"Scheduled execution details: cron={cron_expression}, tz={timezone}, user_tz={user_timezone}")
    
    try:
        # Get cron API key for the project
        with get_db_session() as session:
            cron_api_key = get_existing_cron_api_key(session, UUID(project_id))
            
            if not cron_api_key or not cron_api_key.is_active:
                error_msg = f"No active cron API key found for project {project_id}"
                LOGGER.error(error_msg)
                return {
                    "status": "FAILED",
                    "error": error_msg,
                    "task_id": task_id,
                    "project_id": project_id,
                    "execution_time": (datetime.utcnow() - start_time).total_seconds()
                }
            
            raw_api_key = cron_api_key.get_raw_key()
            if not raw_api_key:
                error_msg = f"Could not retrieve raw API key for project {project_id}"
                LOGGER.error(error_msg)
                return {
                    "status": "FAILED", 
                    "error": error_msg,
                    "task_id": task_id,
                    "project_id": project_id,
                    "execution_time": (datetime.utcnow() - start_time).total_seconds()
                }
        
        # Prepare input data for the workflow
        input_data = {
            "messages": [
                {
                    "role": "user",
                    "content": f"Scheduled execution triggered at {start_time.isoformat()} UTC"
                }
            ],
            "scheduled": True,  # Flag to indicate this is a scheduled execution
            "scheduled_execution_metadata": {
                "task_id": task_id,
                "cron_expression": cron_expression,
                "timezone": timezone,
                "user_timezone": user_timezone,
                "triggered_at": start_time.isoformat(),
                "graph_runner_id": graph_runner_id,
                "scheduler_id": scheduler_id,
                "schedule_created_at": created_at
            }
        }
        
        # Make HTTP request to production endpoint
        result = make_inference_request(
            project_id=project_id,
            api_key=raw_api_key,
            input_data=input_data,
            timeout=600  # 10 minutes timeout for workflow execution
        )
        
        execution_time = (datetime.utcnow() - start_time).total_seconds()
        
        if result["status"] == "SUCCESS":
            LOGGER.info(f"Scheduled workflow execution completed successfully: task={task_id}, project={project_id}, time={execution_time}s")
            return {
                "status": "SUCCESS",
                "task_id": task_id,
                "project_id": project_id,
                "graph_runner_id": graph_runner_id,
                "scheduler_id": scheduler_id,
                "execution_time": execution_time,
                "result": result["result"],
                "http_status_code": result["status_code"]
            }
        else:
            error_msg = f"Scheduled workflow execution failed: {result.get('error', 'Unknown error')}"
            LOGGER.error(f"{error_msg}: task={task_id}, project={project_id}")
            return {
                "status": "FAILED",
                "error": error_msg,
                "task_id": task_id,
                "project_id": project_id,
                "graph_runner_id": graph_runner_id,
                "scheduler_id": scheduler_id,
                "execution_time": execution_time,
                "http_status_code": result.get("status_code")
            }
            
    except Exception as e:
        execution_time = (datetime.utcnow() - start_time).total_seconds()
        error_msg = f"Exception in scheduled workflow execution: {str(e)}"
        LOGGER.error(f"{error_msg}: task={task_id}, project={project_id}", exc_info=True)
        
        return {
            "status": "FAILED",
            "error": error_msg,
            "task_id": task_id,
            "project_id": project_id,
            "graph_runner_id": graph_runner_id,
            "scheduler_id": scheduler_id,
            "execution_time": execution_time
        }


@celery_app.task(name="cleanup_old_executions")
def cleanup_old_executions(days_to_keep: int = 90) -> Dict[str, Any]:
    """
    Clean up old execution records.
    This is a system maintenance task that runs daily.
    
    Args:
        days_to_keep: Number of days of execution records to keep
        
    Returns:
        Cleanup result
    """
    LOGGER.info(f"Starting cleanup of execution records older than {days_to_keep} days")
    
    try:
        # Note: With the simplified approach, we don't have a separate executions table
        # Execution history is stored in Celery's result backend (Redis) or can be logged
        # This task can be used for other cleanup operations if needed
        
        LOGGER.info("Cleanup completed (no separate executions table in simplified approach)")
        
        return {
            "status": "SUCCESS",
            "message": "Cleanup completed",
            "days_to_keep": days_to_keep,
            "method": "simplified_django_celery_beat_only"
        }
        
    except Exception as e:
        error_msg = f"Failed to cleanup old executions: {str(e)}"
        LOGGER.error(error_msg, exc_info=True)
        return {
            "status": "FAILED",
            "error": error_msg,
            "days_to_keep": days_to_keep
        }
