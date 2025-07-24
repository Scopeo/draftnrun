"""
Service for managing cron job specific API keys.
Handles creation, update, and deletion of API keys specifically for scheduled workflows.
"""

import logging
from typing import Optional, Dict, Any
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from ada_backend.services.api_key_service import generate_api_key, deactivate_api_key_service
from ada_backend.repositories.api_key_repository import get_api_keys_by_project_id, get_api_key_by_id
from ada_backend.database import models as db

LOGGER = logging.getLogger(__name__)

CRON_API_KEY_PREFIX = "cron_job_automatic_name"


def generate_cron_job_uuid() -> str:
    """Generate a unique UUID for cron job API keys."""
    return str(uuid4())


def create_cron_api_key_name(cron_job_uuid: str) -> str:
    """Create a standardized name for cron job API keys."""
    return f"{CRON_API_KEY_PREFIX}{cron_job_uuid}"


def get_existing_cron_api_key(session: Session, project_id: UUID) -> Optional[db.ApiKey]:
    """
    Get existing cron job API key for a project.
    
    Args:
        session: Database session
        project_id: Project UUID
        
    Returns:
        Existing cron API key or None
    """
    api_keys = get_api_keys_by_project_id(session, project_id)
    
    for api_key in api_keys:
        if api_key.name.startswith(CRON_API_KEY_PREFIX):
            return api_key
    
    return None


def generate_cron_api_key_for_project(
    session: Session, 
    project_id: UUID,
    creator_user_id: UUID
) -> Dict[str, Any]:
    """
    Generate a new cron job API key for a project.
    
    Args:
        session: Database session
        project_id: Project UUID  
        creator_user_id: User UUID creating the key (system user for cron jobs)
        
    Returns:
        Dict with API key information
    """
    cron_job_uuid = generate_cron_job_uuid()
    key_name = create_cron_api_key_name(cron_job_uuid)
    
    try:
        api_key_response = generate_api_key(
            session=session,
            project_id=project_id,
            key_name=key_name,
            creator_user_id=creator_user_id
        )
        
        # Store the raw API key in encrypted form for cron jobs
        api_key_record = get_api_key_by_id(session, api_key_response.key_id)
        if api_key_record:
            api_key_record.set_raw_key(api_key_response.private_key)
            session.commit()
            LOGGER.info(f"Stored encrypted raw API key for cron job {cron_job_uuid}")
        else:
            raise ValueError(f"Failed to retrieve created API key with ID {api_key_response.key_id}")
        
        LOGGER.info(f"Generated cron API key for project {project_id} with UUID {cron_job_uuid}")
        
        return {
            "status": "SUCCESS",
            "cron_job_uuid": cron_job_uuid,
            "api_key": api_key_response.private_key,
            "key_id": api_key_response.key_id,
            "key_name": key_name
        }
        
    except Exception as e:
        error_msg = f"Failed to generate cron API key for project {project_id}: {str(e)}"
        LOGGER.error(error_msg, exc_info=True)
        return {
            "status": "FAILED",
            "error": error_msg
        }


def update_cron_api_key_for_project(
    session: Session,
    project_id: UUID, 
    creator_user_id: UUID
) -> Dict[str, Any]:
    """
    Update cron API key for a project by deactivating old key and creating new one.
    
    Args:
        session: Database session
        project_id: Project UUID
        creator_user_id: User UUID creating the new key
        
    Returns:
        Dict with update results
    """
    results = {
        "status": "SUCCESS",
        "old_key_deactivated": False,
        "new_key_created": False,
        "error": None
    }
    
    # Deactivate existing cron API key if it exists
    existing_key = get_existing_cron_api_key(session, project_id)
    if existing_key:
        try:
            deactivate_api_key_service(
                session=session,
                key_id=existing_key.id,
                revoker_user_id=creator_user_id
            )
            results["old_key_deactivated"] = True
            LOGGER.info(f"Deactivated old cron API key {existing_key.id} for project {project_id}")
        except Exception as e:
            error_msg = f"Failed to deactivate old cron API key: {str(e)}"
            LOGGER.error(error_msg, exc_info=True)
            results["error"] = error_msg
            results["status"] = "PARTIAL"
    
    # Generate new cron API key
    try:
        new_key_result = generate_cron_api_key_for_project(
            session=session,
            project_id=project_id,
            creator_user_id=creator_user_id
        )
        
        if new_key_result["status"] == "SUCCESS":
            results["new_key_created"] = True
            results.update(new_key_result)
        else:
            results["error"] = new_key_result.get("error", "Unknown error creating new key")
            results["status"] = "FAILED" if not results["old_key_deactivated"] else "PARTIAL"
            
    except Exception as e:
        error_msg = f"Failed to create new cron API key: {str(e)}"
        LOGGER.error(error_msg, exc_info=True)
        results["error"] = error_msg
        results["status"] = "FAILED" if not results["old_key_deactivated"] else "PARTIAL"
    
    return results


def cleanup_cron_api_keys_for_project(
    session: Session,
    project_id: UUID,
    revoker_user_id: UUID
) -> Dict[str, Any]:
    """
    Clean up all cron API keys for a project.
    
    Args:
        session: Database session
        project_id: Project UUID
        revoker_user_id: User UUID revoking the keys
        
    Returns:
        Dict with cleanup results
    """
    existing_key = get_existing_cron_api_key(session, project_id)
    
    if not existing_key:
        return {
            "status": "SUCCESS",
            "message": "No cron API keys found to clean up",
            "keys_deactivated": 0
        }
    
    try:
        deactivate_api_key_service(
            session=session,
            key_id=existing_key.id,
            revoker_user_id=revoker_user_id
        )
        
        LOGGER.info(f"Cleaned up cron API key {existing_key.id} for project {project_id}")
        
        return {
            "status": "SUCCESS",
            "message": "Cron API key cleaned up successfully",
            "keys_deactivated": 1
        }
        
    except Exception as e:
        error_msg = f"Failed to cleanup cron API key: {str(e)}"
        LOGGER.error(error_msg, exc_info=True)
        return {
            "status": "FAILED",
            "error": error_msg,
            "keys_deactivated": 0
        } 