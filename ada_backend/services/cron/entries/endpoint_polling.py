"""
Endpoint polling cron entry: models, validators, executor, and spec.

This cron job queries a GET endpoint to fetch data with values,
compares them with existing values stored in the ingestion database,
and identifies new values (endpoint_values - stored_values).
"""

import logging
import json
from typing import Any, Optional
from uuid import UUID
from pydantic import Field, HttpUrl

import httpx

from ada_backend.repositories.tracker_history_repository import (
    create_tracked_values_bulk,
    get_tracked_values_history,
)
from ada_backend.services.cron.core import BaseUserPayload, BaseExecutionPayload, CronEntrySpec
from ada_backend.services.cron.errors import CronValidationError
from ada_backend.repositories.project_repository import get_project
from ada_backend.services.agent_runner_service import run_env_agent
from ada_backend.database.models import CallType, EnvType

LOGGER = logging.getLogger(__name__)


class EndpointPollingUserPayload(BaseUserPayload):
    """User input for endpoint polling cron jobs."""

    endpoint_url: HttpUrl = Field(..., description="GET endpoint URL to query for values")
    tracking_field_path: str = Field(
        default="id",
        description="Path to the tracking field in the response (e.g., 'id', 'data[].id', 'items[].id')",
    )
    filter_fields: Optional[dict[str, str]] = Field(
        default=None,
        description=(
            "Dictionary mapping filter field paths to their target values (e.g., "
            "{'data[].status': 'processing', 'data[].priority': 'high'}). "
            "Only values matching all filter conditions will be tracked."
        ),
    )
    headers: Optional[dict[str, str]] = Field(default=None, description="Optional HTTP headers for the request")
    timeout: int = Field(default=30, ge=1, le=300, description="Request timeout in seconds")
    project_id: Optional[UUID] = Field(
        default=None,
        description=("Project ID to trigger workflows for each new value detected."),
    )
    env: EnvType = Field(
        default=EnvType.PRODUCTION,
        description="Environment (draft/production) for workflow execution",
    )
    workflow_input_template: Optional[str] = Field(
        default=None,
        description=(
            "Template for the workflow input message. Use {id} for the detected value "
            "and {item} for the full item (JSON). If None, defaults to just the item JSON."
        ),
    )

    class Config:
        json_schema_extra = {
            "example": {
                "endpoint_url": "https://api.example.com/items",
                "tracking_field_path": "data[].id",
                "filter_fields": {"data[].status": "processing"},
                "headers": {"Authorization": "Bearer token"},
                "timeout": 30,
                "project_id": "123e4567-e89b-12d3-a456-426614174000",
                "env": "production",
                "workflow_input_template": "Process item: {item}",
            }
        }


class EndpointPollingExecutionPayload(BaseExecutionPayload):
    """Execution payload stored in database for endpoint polling jobs."""

    endpoint_url: str
    tracking_field_path: str
    filter_fields: Optional[dict[str, str]] = None
    headers: Optional[dict[str, str]]
    timeout: int
    organization_id: UUID
    created_by: UUID
    project_id: Optional[UUID] = None
    env: EnvType = EnvType.PRODUCTION
    workflow_input_template: Optional[str] = None


def validate_registration(
    user_input: EndpointPollingUserPayload, organization_id: UUID, user_id: UUID, **kwargs
) -> EndpointPollingExecutionPayload:
    """
    Validate user input and return the execution payload
    that will be used to execute the job.
    Table names are generated dynamically using organization_id and cron_id during execution.

    This function also validates that:
    - The endpoint is accessible and returns valid JSON
    - The tracking_field_path can successfully extract IDs from the response
    - If filter_fields are provided, they can be extracted from the response
    """
    if not organization_id:
        raise ValueError("organization_id missing from context")

    if not user_id:
        raise ValueError("user_id missing from context")

    db = kwargs.get("db")
    if not db:
        raise ValueError("db missing from context")

    # If project_id is provided, validate it exists and belongs to the organization
    if user_input.project_id:
        project = get_project(db, project_id=user_input.project_id)
        if not project:
            raise ValueError(f"Project {user_input.project_id} not found")
        if project.organization_id != organization_id:
            raise ValueError(f"Project {user_input.project_id} does not belong to organization {organization_id}")

    # Validate endpoint accessibility and ID extraction
    LOGGER.info(f"Validating endpoint polling configuration: {user_input.endpoint_url}")
    try:
        with httpx.Client(timeout=user_input.timeout) as client:
            response = client.get(
                str(user_input.endpoint_url),
                headers=user_input.headers,
            )
            response.raise_for_status()

            try:
                endpoint_data = response.json()
            except json.JSONDecodeError as e:
                raise CronValidationError(
                    f"Endpoint {user_input.endpoint_url} returned invalid JSON: {e}. "
                    f"Response status: {response.status_code}, "
                    f"Content-Type: {response.headers.get('content-type', 'unknown')}"
                ) from e

            # Validate tracking_field_path extraction
            try:
                extracted_ids = _extract_ids_from_response(endpoint_data, user_input.tracking_field_path)
                if not extracted_ids:
                    LOGGER.warning(
                        f"Endpoint {user_input.endpoint_url} returned no IDs "
                        f"using path '{user_input.tracking_field_path}'. "
                        f"This may be expected if the endpoint is currently empty."
                    )
                else:
                    LOGGER.info(
                        f"Successfully extracted {len(extracted_ids)} IDs from endpoint "
                        f"using path '{user_input.tracking_field_path}'"
                    )
            except ValueError as e:
                raise CronValidationError(
                    f"Failed to extract IDs from endpoint {user_input.endpoint_url} "
                    f"using path '{user_input.tracking_field_path}': {e}. "
                    f"Please verify the path is correct for the endpoint response structure."
                ) from e

            # Validate filter_fields extraction if provided
            if user_input.filter_fields:
                if "[]" not in user_input.tracking_field_path:
                    raise CronValidationError(
                        "filter_fields can only be used when tracking_field_path "
                        "uses array notation (e.g., 'data[].id'), "
                        f"but got '{user_input.tracking_field_path}'"
                    )

                filter_field_paths = list(user_input.filter_fields.keys())
                try:
                    items_with_filter_values = _extract_ids_and_filter_values_from_response(
                        endpoint_data, user_input.tracking_field_path, filter_field_paths
                    )

                    # Check if any items match the filter conditions
                    matching_ids = _filter_matching_items(items_with_filter_values, user_input.filter_fields)
                    matching_count = len(matching_ids)

                    LOGGER.info(
                        f"Filter validation: {matching_count} items match filter conditions out of "
                        f"{len(items_with_filter_values)} total items"
                    )
                except ValueError as e:
                    raise CronValidationError(
                        f"Failed to extract filter fields from endpoint {user_input.endpoint_url}: {e}. "
                        f"Please verify the filter field paths are correct for the endpoint response structure."
                    ) from e

    except httpx.HTTPStatusError as e:
        raise CronValidationError(
            f"Endpoint {user_input.endpoint_url} returned HTTP {e.response.status_code}: {e.response.text[:200]}. "
            f"Please verify the endpoint URL is correct and accessible."
        ) from e
    except httpx.TimeoutException as e:
        raise CronValidationError(
            f"Timeout while connecting to endpoint {user_input.endpoint_url} (timeout: {user_input.timeout}s). "
            f"Please verify the endpoint is accessible or increase the timeout."
        ) from e
    except httpx.RequestError as e:
        raise CronValidationError(
            f"Failed to connect to endpoint {user_input.endpoint_url}: {e}. "
            f"Please verify the endpoint URL is correct and accessible."
        ) from e
    except CronValidationError:
        # Re-raise validation errors as-is
        raise
    except Exception as e:
        raise CronValidationError(
            f"Unexpected error validating endpoint {user_input.endpoint_url}: {e}. "
            f"Please verify the endpoint configuration is correct."
        ) from e

    return EndpointPollingExecutionPayload(
        endpoint_url=str(user_input.endpoint_url),
        tracking_field_path=user_input.tracking_field_path,
        filter_fields=user_input.filter_fields,
        headers=user_input.headers,
        timeout=user_input.timeout,
        organization_id=organization_id,
        created_by=user_id,
        project_id=user_input.project_id,
        env=user_input.env,
        workflow_input_template=user_input.workflow_input_template,
    )


def validate_execution(execution_payload: EndpointPollingExecutionPayload, **kwargs) -> None:
    """Validate execution payload and return None."""
    db = kwargs.get("db")
    if not db:
        raise ValueError("db missing from context")

    # If project_id is provided, validate it still exists and belongs to the organization
    if execution_payload.project_id:
        project = get_project(db, project_id=execution_payload.project_id)
        if not project:
            raise ValueError(f"Project {execution_payload.project_id} not found at execution time")
        if project.organization_id != execution_payload.organization_id:
            raise ValueError("Project organization mismatch at execution time")


def _extract_nested_path(data: Any, path: str) -> Any:
    """
    Extract value from nested path in data structure.

    Supports paths like:
    - "data" -> data["data"]
    - "data.items" -> data["data"]["items"]
    - Works with dict and object attributes
    """
    current = data
    for key in path.split("."):
        if key:
            if isinstance(current, dict):
                current = current.get(key)
            elif hasattr(current, key):
                current = getattr(current, key)
            else:
                return None
    return current


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

    current = _extract_nested_path(data, array_path)
    if current is None:
        raise ValueError(f"Array path '{array_path}' returned None")

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


def _extract_items_with_ids(data: Any, tracking_field_path: str) -> dict[str, dict[str, Any]]:
    """
    Extract all items from response with their values.

    Returns a dictionary mapping item_value -> complete item.
    """
    items_by_id: dict[str, dict[str, Any]] = {}

    if "[]" in tracking_field_path:
        # Array notation: extract all items from array
        id_parts = tracking_field_path.split("[]")
        if len(id_parts) == 2:
            array_path = id_parts[0].rstrip(".")
            id_field = id_parts[1].lstrip(".")

            # Extract the array
            current = _extract_nested_path(data, array_path)
            if isinstance(current, list):
                for item in current:
                    if isinstance(item, dict) and id_field in item:
                        item_id = str(item.get(id_field, ""))
                        if item_id:
                            items_by_id[item_id] = item
    else:
        # Simple path: extract single item
        if isinstance(data, dict):
            # Try to get the item directly
            if tracking_field_path in data:
                item_id = str(data[tracking_field_path])
                if item_id:
                    items_by_id[item_id] = data
            else:
                # Try nested path
                path_parts = tracking_field_path.split(".")
                if len(path_parts) > 1:
                    # Get parent object
                    parent_path = ".".join(path_parts[:-1])
                    current = _extract_nested_path(data, parent_path)
                    if isinstance(current, dict):
                        id_field = path_parts[-1]
                        if id_field in current:
                            item_id = str(current[id_field])
                            if item_id:
                                items_by_id[item_id] = current

    return items_by_id


def _extract_ids_and_filter_values_from_response(
    data: Any, tracking_field_path: str, filter_field_paths: list[str]
) -> dict[str, dict[str, Any]]:
    """
    Extract values and their corresponding filter field values from API response.
    Used only for filtering - filter_values are not saved to DB.

    Args:
        data: The API response data
        tracking_field_path: Path to the tracking field (e.g., 'data[].id')
        filter_field_paths: List of paths to filter fields
           (e.g., ['data[].status', 'data[].priority'])

    Returns:
        Dictionary mapping value to a dict containing all filter values.
    """
    if "[]" not in tracking_field_path:
        raise ValueError(
            "tracking_field_path must use array notation (e.g., 'data[].id') when filter fields are provided"
        )

    # Extract the array path from tracking_field_path
    id_parts = tracking_field_path.split("[]")
    if len(id_parts) != 2:
        raise ValueError(f"Invalid tracking_field_path format: {tracking_field_path}")

    array_path = id_parts[0].rstrip(".")
    id_field = id_parts[1].lstrip(".")

    # Extract the array
    current = _extract_nested_path(data, array_path)
    if current is None:
        raise ValueError(f"Array path '{array_path}' not found in response")

    if not isinstance(current, list):
        raise ValueError(f"Path '{array_path}' does not point to an array")

    # Extract filter field names from paths
    filter_field_extractors = []
    for filter_field_path in filter_field_paths:
        filter_parts = filter_field_path.split("[]")
        if len(filter_parts) != 2:
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
                "item": item,  # Store the complete item
            }

    return result


def _filter_matching_items(
    items_with_filter_values: dict[str, dict[str, Any]], filter_fields: dict[str, str]
) -> set[str]:
    """
    Filter items that match all filter conditions.

    Args:
        items_with_filter_values: Dictionary mapping item_id to dict with filter_values
        filter_fields: Dictionary mapping filter field paths to target values

    Returns:
        Set of item IDs that match all filter conditions
    """
    matching_ids = set()
    for item_id, item_data in items_with_filter_values.items():
        filter_values = item_data.get("filter_values", {})
        matches_all = all(
            filter_values.get(field_path) == target_value for field_path, target_value in filter_fields.items()
        )
        if matches_all:
            matching_ids.add(item_id)
    return matching_ids


async def execute(execution_payload: EndpointPollingExecutionPayload, **kwargs) -> dict[str, Any]:
    db = kwargs.get("db")
    if not db:
        raise ValueError("db missing from context")

    cron_id = kwargs.get("cron_id")
    if not cron_id:
        raise ValueError("cron_id is required")

    LOGGER.info(f"Starting endpoint polling for endpoint {execution_payload.endpoint_url}")

    # Step 1: Query the endpoint
    LOGGER.info(f"Querying endpoint: {execution_payload.endpoint_url}")
    async with httpx.AsyncClient(timeout=execution_payload.timeout) as client:
        response = await client.get(
            execution_payload.endpoint_url,
            headers=execution_payload.headers,
        )
        response.raise_for_status()
        endpoint_data = response.json()

    items_by_id = _extract_items_with_ids(endpoint_data, execution_payload.tracking_field_path)

    filter_fields = execution_payload.filter_fields
    if filter_fields:
        filter_field_paths = list(filter_fields.keys())
        items_with_filter_values = _extract_ids_and_filter_values_from_response(
            endpoint_data, execution_payload.tracking_field_path, filter_field_paths
        )

        polled_values = _filter_matching_items(items_with_filter_values, filter_fields)

        LOGGER.info(
            f"Found {len(polled_values)} values matching filter "
            f"conditions out of {len(items_with_filter_values)} total values"
        )
    else:
        polled_values = _extract_ids_from_response(endpoint_data, execution_payload.tracking_field_path)
        LOGGER.info(f"Found {len(polled_values)} values from endpoint")

    stored_history = get_tracked_values_history(db, cron_id)
    stored_ids = {str(record.tracked_value) for record in stored_history}
    LOGGER.info(f"Found {len(stored_ids)} already processed values")

    new_values = polled_values - stored_ids
    removed_ids = stored_ids - polled_values
    if new_values:
        create_tracked_values_bulk(
            session=db,
            cron_id=cron_id,
            tracked_values=list(new_values),
        )

    LOGGER.info(f"Identified {len(new_values)} new values and {len(removed_ids)} removed values")

    workflow_results = []
    if execution_payload.project_id and new_values:
        LOGGER.info(f"Triggering workflows for {len(new_values)} new values in project {execution_payload.project_id}")
        for new_value in new_values:
            try:
                item = items_by_id.get(new_value, {})
                if execution_payload.workflow_input_template:
                    item_json = json.dumps(item, default=str) if item else "{}"
                    input_message = execution_payload.workflow_input_template.format(id=new_value, item=item_json)
                else:
                    if item:
                        input_message = json.dumps(item, default=str)
                    else:
                        input_message = str(new_value)

                input_data = {
                    "messages": [
                        {"role": "user", "content": input_message},
                    ],
                    "item": item,  # Pass item as separate field for easy access
                }
                workflow_result = await run_env_agent(
                    session=db,
                    project_id=execution_payload.project_id,
                    env=execution_payload.env,
                    input_data=input_data,
                    call_type=CallType.API,
                )
                workflow_results.append(
                    {
                        "id": new_value,
                        "status": "success",
                        "message": workflow_result.message,
                        "trace_id": workflow_result.trace_id,
                    }
                )
                LOGGER.info(f"Successfully triggered workflow for value {new_value}")
            except Exception as e:
                LOGGER.error(f"Failed to trigger workflow for value {new_value}: {e}")
                workflow_results.append(
                    {
                        "id": new_value,
                        "status": "error",
                        "error": str(e),
                    }
                )

    return {
        "endpoint_url": execution_payload.endpoint_url,
        "total_polled_values": len(polled_values),
        "total_stored_ids": len(stored_ids),
        "new_values_count": len(new_values),
        "removed_ids_count": len(removed_ids),
        "new_values": sorted(list(new_values)) if new_values else [],
        "removed_ids": sorted(list(removed_ids)) if removed_ids else [],
        "workflows_triggered": workflow_results,
    }


spec = CronEntrySpec(
    user_payload_model=EndpointPollingUserPayload,
    execution_payload_model=EndpointPollingExecutionPayload,
    registration_validator=validate_registration,
    execution_validator=validate_execution,
    executor=execute,
)
