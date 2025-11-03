"""
Endpoint ID tracker cron entry: models, validators, executor, and spec.

This cron job queries a GET endpoint to fetch data with IDs,
compares them with existing IDs stored in the ingestion database,
and identifies new IDs (endpoint_ids - stored_ids).
"""

import logging
from typing import Any, Optional
from uuid import UUID
from pydantic import Field, HttpUrl
import httpx
from sqlalchemy.orm import Session

from ada_backend.services.cron.core import BaseUserPayload, BaseExecutionPayload, CronEntrySpec
from ada_backend.repositories.source_repository import get_data_source_by_id, get_source_attributes
from ada_backend.repositories.cron_repository import get_cron_runs_by_cron_id
from ada_backend.database.models import CronStatus
from engine.storage_service.local_service import SQLLocalService
from settings import settings

LOGGER = logging.getLogger(__name__)


class EndpointIdTrackerUserPayload(BaseUserPayload):
    """User input for endpoint ID tracker cron jobs."""

    endpoint_url: HttpUrl = Field(..., description="GET endpoint URL to query for IDs")
    source_id: UUID = Field(..., description="DataSource ID that stores ingested IDs")
    id_field_path: str = Field(
        default="id",
        description="Path to the ID field in the response (e.g., 'id', 'data[].id', 'items[].id')",
    )
    step_field_path: Optional[str] = Field(
        default=None,
        description="Path to the step field in the response (e.g., 'step', 'data[].step', 'items[].status'). If provided, will filter to track items that just arrived in target_step.",
    )
    target_step: Optional[str] = Field(
        default=None,
        description="Target step value to track. Only items that just arrived in this step will be returned. Required if step_field_path is provided.",
    )
    headers: Optional[dict[str, str]] = Field(default=None, description="Optional HTTP headers for the request")
    timeout: int = Field(default=30, ge=1, le=300, description="Request timeout in seconds")

    class Config:
        json_schema_extra = {
            "example": {
                "endpoint_url": "https://api.example.com/items",
                "source_id": "123e4567-e89b-12d3-a456-426614174000",
                "id_field_path": "data[].id",
                "step_field_path": "data[].step",
                "target_step": "processing",
                "headers": {"Authorization": "Bearer token"},
                "timeout": 30,
            }
        }


class EndpointIdTrackerExecutionPayload(BaseExecutionPayload):
    """Execution payload stored in database for endpoint ID tracker jobs."""

    endpoint_url: str
    source_id: UUID
    id_field_path: str
    step_field_path: Optional[str]
    target_step: Optional[str]
    headers: Optional[dict[str, str]]
    timeout: int
    organization_id: UUID
    created_by: UUID


def validate_registration(
    user_input: EndpointIdTrackerUserPayload, organization_id: UUID, user_id: UUID, **kwargs
) -> EndpointIdTrackerExecutionPayload:
    """
    Validate user input and return the execution payload
    that will be used to execute the job.
    """
    if not organization_id:
        raise ValueError("organization_id missing from context")

    if not user_id:
        raise ValueError("user_id missing from context")

    db = kwargs.get("db")
    if not db:
        raise ValueError("db missing from context")

    # Verify source exists and belongs to the organization
    source = get_data_source_by_id(db, user_input.source_id)
    if not source:
        raise ValueError(f"DataSource not found: {user_input.source_id}")

    if source.organization_id != organization_id:
        raise ValueError("DataSource does not belong to the specified organization")

    # Verify source has ingestion database configuration
    if not source.database_schema or not source.database_table_name:
        raise ValueError(
            f"DataSource {user_input.source_id} is missing database_schema or database_table_name. "
            "This source must have ingestion database configuration."
        )

    # Validate step filter configuration
    if user_input.step_field_path and not user_input.target_step:
        raise ValueError("target_step is required when step_field_path is provided")

    if user_input.target_step and not user_input.step_field_path:
        raise ValueError("step_field_path is required when target_step is provided")

    return EndpointIdTrackerExecutionPayload(
        endpoint_url=str(user_input.endpoint_url),
        source_id=user_input.source_id,
        id_field_path=user_input.id_field_path,
        step_field_path=user_input.step_field_path,
        target_step=user_input.target_step,
        headers=user_input.headers,
        timeout=user_input.timeout,
        organization_id=organization_id,
        created_by=user_id,
    )


def validate_execution(execution_payload: EndpointIdTrackerExecutionPayload, **kwargs) -> None:
    """Validate execution payload and return None."""
    db = kwargs.get("db")
    if not db:
        raise ValueError("db missing from context")

    # Ensure source still exists and belongs to the same organization
    source = get_data_source_by_id(db, execution_payload.source_id)
    if not source:
        raise ValueError("DataSource not found at execution time")

    if source.organization_id != execution_payload.organization_id:
        raise ValueError("DataSource organization mismatch at execution time")

    if not source.database_schema or not source.database_table_name:
        raise ValueError("DataSource missing ingestion database configuration at execution time")


def _extract_field_from_response(data: Any, field_path: str) -> Any:
    """
    Extract field value from API response using field path.

    For array paths, returns a dictionary mapping ID to field value.
    For simple paths, returns the single value.

    Supports paths like:
    - "id" -> data["id"] or data.id
    - "data[].id" -> {item["id"]: ... for item in data["data"]}
    - "items[].id" -> {item["id"]: ... for item in data["items"]}
    """
    if not field_path:
        raise ValueError("field_path cannot be empty")

    # Simple path without array notation
    if "[]" not in field_path:
        if isinstance(data, dict):
            if field_path in data:
                return data[field_path]
            else:
                raise ValueError(f"Field path '{field_path}' not found in response")
        elif hasattr(data, field_path):
            return getattr(data, field_path)
        else:
            raise ValueError(f"Field path '{field_path}' not found in response")

    # Array notation path like "data[].id" or "items[].id"
    parts = field_path.split("[]")
    if len(parts) != 2:
        raise ValueError(f"Invalid field path format: {field_path}")

    array_path = parts[0]
    nested_field = parts[1].lstrip(".")

    # Navigate to the array
    current = data
    for key in array_path.split("."):
        if key:
            if isinstance(current, dict):
                current = current.get(key)
            elif hasattr(current, key):
                current = getattr(current, key)
            else:
                raise ValueError(f"Path '{key}' not found in response")

    if current is None:
        raise ValueError(f"Array path '{array_path}' returned None")

    # Extract values from array items
    if not isinstance(current, list):
        raise ValueError(f"Path '{array_path}' does not point to an array")

    result = {}
    for item in current:
        if isinstance(item, dict):
            if nested_field in item:
                # For arrays, we need to extract both ID and the field value
                # But we don't know the ID field here, so we'll return the full item
                result[str(item.get(nested_field, ""))] = item
            elif not nested_field:
                result[str(item)] = item
        elif hasattr(item, nested_field):
            result[str(getattr(item, nested_field))] = item
        elif not nested_field:
            result[str(item)] = item

    return result


def _extract_ids_from_response(data: Any, field_path: str) -> set[str]:
    """
    Extract IDs from API response using field path.

    Supports paths like:
    - "id" -> data["id"] or data.id
    - "data[].id" -> [item["id"] for item in data["data"]]
    - "items[].id" -> [item["id"] for item in data["items"]]
    """
    if not field_path:
        raise ValueError("field_path cannot be empty")

    # Simple path without array notation
    if "[]" not in field_path:
        if isinstance(data, dict):
            if field_path in data:
                return {str(data[field_path])}
            else:
                raise ValueError(f"Field path '{field_path}' not found in response")
        elif hasattr(data, field_path):
            return {str(getattr(data, field_path))}
        else:
            raise ValueError(f"Field path '{field_path}' not found in response")

    # Array notation path like "data[].id" or "items[].id"
    parts = field_path.split("[]")
    if len(parts) != 2:
        raise ValueError(f"Invalid field path format: {field_path}")

    array_path = parts[0]
    nested_field = parts[1].lstrip(".")

    # Navigate to the array
    current = data
    for key in array_path.split("."):
        if key:
            if isinstance(current, dict):
                current = current.get(key)
            elif hasattr(current, key):
                current = getattr(current, key)
            else:
                raise ValueError(f"Path '{key}' not found in response")

    if current is None:
        raise ValueError(f"Array path '{array_path}' returned None")

    # Extract IDs from array items
    if not isinstance(current, list):
        raise ValueError(f"Path '{array_path}' does not point to an array")

    ids = set()
    for item in current:
        if isinstance(item, dict):
            if nested_field in item:
                ids.add(str(item[nested_field]))
            elif not nested_field:  # If no nested field, use the item itself
                ids.add(str(item))
        elif hasattr(item, nested_field):
            ids.add(str(getattr(item, nested_field)))
        elif not nested_field:
            ids.add(str(item))

    return ids


def _extract_ids_and_steps_from_response(
    data: Any, id_field_path: str, step_field_path: str
) -> dict[str, dict[str, Any]]:
    """
    Extract IDs and their corresponding step values from API response.

    Returns a dictionary mapping ID to a dict containing the step value and full item data.
    """
    if "[]" not in id_field_path:
        raise ValueError("id_field_path must use array notation (e.g., 'data[].id') when step_field_path is provided")

    # Extract the array path from id_field_path
    id_parts = id_field_path.split("[]")
    if len(id_parts) != 2:
        raise ValueError(f"Invalid id_field_path format: {id_field_path}")

    array_path = id_parts[0].rstrip(".")
    id_field = id_parts[1].lstrip(".")

    # Extract the array
    current = data
    for key in array_path.split("."):
        if key:
            if isinstance(current, dict):
                current = current.get(key)
            elif hasattr(current, key):
                current = getattr(current, key)
            else:
                raise ValueError(f"Array path '{key}' not found in response")

    if not isinstance(current, list):
        raise ValueError(f"Path '{array_path}' does not point to an array")

    # Extract step field path components
    step_parts = step_field_path.split("[]")
    if len(step_parts) != 2:
        # If step path doesn't have array notation, assume it's relative to each item
        step_field = step_field_path.lstrip(".")
    else:
        step_field = step_parts[1].lstrip(".")

    result = {}
    for item in current:
        if isinstance(item, dict):
            item_id = str(item.get(id_field, ""))
            if not item_id:
                continue

            # Extract step value
            step_value = None
            if step_field in item:
                step_value = str(item[step_field])
            elif hasattr(item, step_field):
                step_value = str(getattr(item, step_field))

            result[item_id] = {
                "step": step_value,
                "data": item,
            }

    return result


async def execute(execution_payload: EndpointIdTrackerExecutionPayload, **kwargs) -> dict[str, Any]:
    """
    Execute the endpoint ID tracker job:
    1. Query the GET endpoint to fetch data with IDs
    2. Extract IDs and optionally steps from the response
    3. Get previous run state (if step filtering is enabled)
    4. Get existing IDs from the ingestion database
    5. Compare and identify new IDs or IDs that just arrived in target_step
    """
    db = kwargs.get("db")
    if not db:
        raise ValueError("db missing from context")

    cron_id = kwargs.get("cron_id")
    if execution_payload.step_field_path and execution_payload.target_step and not cron_id:
        raise ValueError("cron_id is required when step filtering is enabled")

    LOGGER.info(f"Starting endpoint ID tracker for source {execution_payload.source_id}")

    # Get source configuration
    source = get_data_source_by_id(db, execution_payload.source_id)
    if not source:
        raise ValueError(f"DataSource {execution_payload.source_id} not found")

    # Step 1: Query the endpoint
    LOGGER.info(f"Querying endpoint: {execution_payload.endpoint_url}")
    async with httpx.AsyncClient(timeout=execution_payload.timeout) as client:
        response = await client.get(
            execution_payload.endpoint_url,
            headers=execution_payload.headers,
        )
        response.raise_for_status()
        endpoint_data = response.json()

    # Step 2: Extract IDs and steps from the response
    if execution_payload.step_field_path and execution_payload.target_step:
        # Extract IDs with their step values
        items_with_steps = _extract_ids_and_steps_from_response(
            endpoint_data, execution_payload.id_field_path, execution_payload.step_field_path
        )
        endpoint_ids = set(items_with_steps.keys())
        LOGGER.info(f"Found {len(endpoint_ids)} IDs from endpoint with step information")
    else:
        # Simple ID extraction
        endpoint_ids = _extract_ids_from_response(endpoint_data, execution_payload.id_field_path)
        items_with_steps = {}
        LOGGER.info(f"Found {len(endpoint_ids)} IDs from endpoint")

    # Step 3: Get existing IDs from ingestion database
    if not settings.INGESTION_DB_URL:
        raise ValueError("INGESTION_DB_URL is not configured")

    db_service = SQLLocalService(engine_url=settings.INGESTION_DB_URL)

    # Query the ingestion table to get existing IDs
    # Try to use source_identifier (FILE_ID_COLUMN_NAME) first if available,
    # otherwise extract from chunk_id which format is typically: {original_id}_{chunk_index}
    try:
        df = db_service.get_table_df(
            table_name=source.database_table_name,
            schema_name=source.database_schema,
            sql_query_filter=None,
        )

        if df.empty:
            stored_ids = set()
            LOGGER.info("No existing IDs found in ingestion database")
        else:
            stored_ids = set()

            # Prefer source_identifier (FILE_ID_COLUMN_NAME) if available, as it contains the original ID
            if "source_identifier" in df.columns:
                LOGGER.info("Using source_identifier column to extract IDs")
                stored_ids = set(df["source_identifier"].dropna().astype(str).unique())
            elif "chunk_id" in df.columns:
                LOGGER.info("Extracting IDs from chunk_id column")
                # Extract original IDs from chunk_id
                # chunk_id format is typically: {original_id}_{chunk_index}
                chunk_ids = df["chunk_id"].astype(str).unique().tolist()

                for chunk_id in chunk_ids:
                    # If it contains underscore, split and take the prefix (original ID)
                    if "_" in chunk_id:
                        # Split and take everything except the last part (chunk index)
                        parts = chunk_id.rsplit("_", 1)
                        stored_ids.add(parts[0])
                    else:
                        # No underscore, treat the whole chunk_id as the original ID
                        stored_ids.add(chunk_id)
            else:
                LOGGER.warning("Neither source_identifier nor chunk_id column found in ingestion table")
                stored_ids = set()
    except Exception as e:
        LOGGER.error(f"Error querying ingestion database: {e}")
        raise ValueError(f"Failed to query ingestion database: {e}")

    LOGGER.info(f"Found {len(stored_ids)} existing IDs in ingestion database")

    # Step 4: Handle step filtering if enabled
    if execution_payload.step_field_path and execution_payload.target_step:
        # Get previous run to compare step changes
        previous_runs = get_cron_runs_by_cron_id(db, cron_id, limit=1)
        previous_steps = {}

        if previous_runs and len(previous_runs) > 0:
            previous_run = previous_runs[0]
            if previous_run.status == CronStatus.SUCCESS and previous_run.result:
                # Extract previous state from result
                prev_result = previous_run.result
                if isinstance(prev_result, dict) and "items_with_steps" in prev_result:
                    previous_steps = prev_result["items_with_steps"]
                    LOGGER.info(f"Found previous state with {len(previous_steps)} items")

        # Identify items that just arrived in target_step
        # (items that are now in target_step but weren't in target_step before)
        items_just_arrived = []
        for item_id, item_data in items_with_steps.items():
            current_step = item_data.get("step")
            if current_step == execution_payload.target_step:
                previous_step = previous_steps.get(item_id, {}).get("step")
                if previous_step != execution_payload.target_step:
                    # This item just arrived in target_step
                    items_just_arrived.append(
                        {
                            "id": item_id,
                            "step": current_step,
                            "previous_step": previous_step,
                        }
                    )

        LOGGER.info(
            f"Found {len(items_just_arrived)} items that just arrived in step '{execution_payload.target_step}'"
        )

        # Still compare with stored IDs for new items
        new_ids = endpoint_ids - stored_ids
        removed_ids = stored_ids - endpoint_ids

        return {
            "endpoint_url": execution_payload.endpoint_url,
            "source_id": str(execution_payload.source_id),
            "target_step": execution_payload.target_step,
            "total_endpoint_ids": len(endpoint_ids),
            "total_stored_ids": len(stored_ids),
            "new_ids_count": len(new_ids),
            "removed_ids_count": len(removed_ids),
            "items_just_arrived_count": len(items_just_arrived),
            "new_ids": sorted(list(new_ids)) if new_ids else [],
            "removed_ids": sorted(list(removed_ids)) if removed_ids else [],
            "items_just_arrived": items_just_arrived,
            "items_with_steps": {item_id: {"step": data["step"]} for item_id, data in items_with_steps.items()},
        }
    else:
        # Step 4: Compare and identify new IDs (no step filtering)
        new_ids = endpoint_ids - stored_ids
        removed_ids = stored_ids - endpoint_ids

        LOGGER.info(f"Identified {len(new_ids)} new IDs and {len(removed_ids)} removed IDs")

        return {
            "endpoint_url": execution_payload.endpoint_url,
            "source_id": str(execution_payload.source_id),
            "total_endpoint_ids": len(endpoint_ids),
            "total_stored_ids": len(stored_ids),
            "new_ids_count": len(new_ids),
            "removed_ids_count": len(removed_ids),
            "new_ids": sorted(list(new_ids)) if new_ids else [],
            "removed_ids": sorted(list(removed_ids)) if removed_ids else [],
        }


spec = CronEntrySpec(
    user_payload_model=EndpointIdTrackerUserPayload,
    execution_payload_model=EndpointIdTrackerExecutionPayload,
    registration_validator=validate_registration,
    execution_validator=validate_execution,
    executor=execute,
)
