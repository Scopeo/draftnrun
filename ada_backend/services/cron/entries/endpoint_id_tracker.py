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
    filter_field_path: Optional[str] = Field(
        default=None,
        description="Path to a single filter field in the response (e.g., 'status', 'data[].status'). Deprecated: use filter_fields for multiple fields.",
    )
    target_filter_value: Optional[str] = Field(
        default=None,
        description="Target filter value for the single filter field. Deprecated: use filter_fields for multiple fields.",
    )
    filter_fields: Optional[dict[str, str]] = Field(
        default=None,
        description="Dictionary mapping filter field paths to their target values (e.g., {'data[].status': 'processing', 'data[].priority': 'high'}). All conditions must be met for an item to be tracked.",
    )
    headers: Optional[dict[str, str]] = Field(default=None, description="Optional HTTP headers for the request")
    timeout: int = Field(default=30, ge=1, le=300, description="Request timeout in seconds")

    class Config:
        json_schema_extra = {
            "example": {
                "endpoint_url": "https://api.example.com/items",
                "source_id": "123e4567-e89b-12d3-a456-426614174000",
                "id_field_path": "data[].id",
                "filter_fields": {"data[].status": "processing", "data[].priority": "high"},
                "headers": {"Authorization": "Bearer token"},
                "timeout": 30,
            }
        }


class EndpointIdTrackerExecutionPayload(BaseExecutionPayload):
    """Execution payload stored in database for endpoint ID tracker jobs."""

    endpoint_url: str
    source_id: UUID
    id_field_path: str
    filter_field_path: Optional[str]
    target_filter_value: Optional[str]
    filter_fields: Optional[dict[str, str]]
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

    # Normalize filter configuration: convert single field to filter_fields dict if needed
    filter_fields = user_input.filter_fields
    if user_input.filter_field_path and user_input.target_filter_value:
        # Support legacy single field format
        if filter_fields:
            raise ValueError(
                "Cannot use both filter_field_path/target_filter_value and filter_fields. Use filter_fields only."
            )
        filter_fields = {user_input.filter_field_path: user_input.target_filter_value}
    elif user_input.filter_field_path or user_input.target_filter_value:
        raise ValueError(
            "Both filter_field_path and target_filter_value must be provided together (or use filter_fields for multiple fields)"
        )

    return EndpointIdTrackerExecutionPayload(
        endpoint_url=str(user_input.endpoint_url),
        source_id=user_input.source_id,
        id_field_path=user_input.id_field_path,
        filter_field_path=user_input.filter_field_path,
        target_filter_value=user_input.target_filter_value,
        filter_fields=filter_fields,
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


def _extract_ids_and_filter_values_from_response(
    data: Any, id_field_path: str, filter_field_paths: list[str]
) -> dict[str, dict[str, Any]]:
    """
    Extract IDs and their corresponding filter field values from API response.

    Args:
        data: The API response data
        id_field_path: Path to the ID field (e.g., 'data[].id')
        filter_field_paths: List of paths to filter fields (e.g., ['data[].status', 'data[].priority'])

    Returns:
        Dictionary mapping ID to a dict containing all filter values and full item data.
    """
    if "[]" not in id_field_path:
        raise ValueError("id_field_path must use array notation (e.g., 'data[].id') when filter fields are provided")

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

    # Extract filter field names from paths
    filter_field_extractors = []
    for filter_field_path in filter_field_paths:
        filter_parts = filter_field_path.split("[]")
        if len(filter_parts) != 2:
            # If filter path doesn't have array notation, assume it's relative to each item
            filter_field = filter_field_path.lstrip(".")
        else:
            filter_field = filter_parts[1].lstrip(".")
        filter_field_extractors.append((filter_field_path, filter_field))

    result = {}
    for item in current:
        if isinstance(item, dict):
            item_id = str(item.get(id_field, ""))
            if not item_id:
                continue

            # Extract all filter values
            filter_values = {}
            for filter_field_path, filter_field in filter_field_extractors:
                filter_value = None
                if filter_field in item:
                    filter_value = str(item[filter_field])
                elif hasattr(item, filter_field):
                    filter_value = str(getattr(item, filter_field))
                filter_values[filter_field_path] = filter_value

            result[item_id] = {
                "filter_values": filter_values,
                "data": item,
            }

    return result


async def execute(execution_payload: EndpointIdTrackerExecutionPayload, **kwargs) -> dict[str, Any]:
    """
    Execute the endpoint ID tracker job:
    1. Query the GET endpoint to fetch data with IDs
    2. Extract IDs and optionally filter field values from the response
    3. Get previous run state (if filter field filtering is enabled)
    4. Get existing IDs from the ingestion database
    5. Compare and identify new IDs or IDs that just arrived at target_filter_value
    """
    db = kwargs.get("db")
    if not db:
        raise ValueError("db missing from context")

    cron_id = kwargs.get("cron_id")
    # Normalize filter_fields from legacy single field format if needed
    filter_fields = execution_payload.filter_fields
    if execution_payload.filter_field_path and execution_payload.target_filter_value and not filter_fields:
        filter_fields = {execution_payload.filter_field_path: execution_payload.target_filter_value}

    if filter_fields and not cron_id:
        raise ValueError("cron_id is required when filter field filtering is enabled")

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

    # Step 2: Extract IDs and filter values from the response
    if filter_fields:
        # Extract IDs with their filter field values
        filter_field_paths = list(filter_fields.keys())
        items_with_filter_values = _extract_ids_and_filter_values_from_response(
            endpoint_data, execution_payload.id_field_path, filter_field_paths
        )
        endpoint_ids = set(items_with_filter_values.keys())
        LOGGER.info(f"Found {len(endpoint_ids)} IDs from endpoint with filter field information")
    else:
        # Simple ID extraction
        endpoint_ids = _extract_ids_from_response(endpoint_data, execution_payload.id_field_path)
        items_with_filter_values = {}
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

    # Step 4: Handle filter field filtering if enabled
    if filter_fields:
        # Get previous run to compare filter value changes
        previous_runs = get_cron_runs_by_cron_id(db, cron_id, limit=1)
        previous_filter_values = {}

        if previous_runs and len(previous_runs) > 0:
            previous_run = previous_runs[0]
            if previous_run.status == CronStatus.SUCCESS and previous_run.result:
                # Extract previous state from result
                prev_result = previous_run.result
                if isinstance(prev_result, dict) and "items_with_filter_values" in prev_result:
                    previous_filter_values = prev_result["items_with_filter_values"]
                    LOGGER.info(f"Found previous state with {len(previous_filter_values)} items")

        # Identify items that just arrived at all target filter values
        # (items that now match all filter conditions but didn't match all conditions before)
        items_just_arrived = []
        for item_id, item_data in items_with_filter_values.items():
            current_filter_values = item_data.get("filter_values", {})

            # Check if current item matches all filter conditions
            matches_all_current = all(
                current_filter_values.get(field_path) == target_value
                for field_path, target_value in filter_fields.items()
            )

            if matches_all_current:
                # Check previous state
                previous_filter_values_dict = previous_filter_values.get(item_id, {}).get("filter_values", {})
                matches_all_previous = all(
                    previous_filter_values_dict.get(field_path) == target_value
                    for field_path, target_value in filter_fields.items()
                )

                if not matches_all_previous:
                    # This item just arrived at all target filter values
                    items_just_arrived.append(
                        {
                            "id": item_id,
                            "filter_values": current_filter_values,
                            "previous_filter_values": previous_filter_values_dict,
                        }
                    )

        filter_summary = ", ".join([f"{k}={v}" for k, v in filter_fields.items()])
        LOGGER.info(f"Found {len(items_just_arrived)} items that just arrived at filter conditions: {filter_summary}")

        # Still compare with stored IDs for new items
        new_ids = endpoint_ids - stored_ids
        removed_ids = stored_ids - endpoint_ids

        return {
            "endpoint_url": execution_payload.endpoint_url,
            "source_id": str(execution_payload.source_id),
            "filter_fields": filter_fields,
            "total_endpoint_ids": len(endpoint_ids),
            "total_stored_ids": len(stored_ids),
            "new_ids_count": len(new_ids),
            "removed_ids_count": len(removed_ids),
            "items_just_arrived_count": len(items_just_arrived),
            "new_ids": sorted(list(new_ids)) if new_ids else [],
            "removed_ids": sorted(list(removed_ids)) if removed_ids else [],
            "items_just_arrived": items_just_arrived,
            "items_with_filter_values": {
                item_id: {"filter_values": data.get("filter_values", {})}
                for item_id, data in items_with_filter_values.items()
            },
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
