"""
Endpoint polling cron entry: models, validators, executor, and spec.

This cron job queries a GET endpoint to fetch data with values,
compares them with existing values stored in the ingestion database,
and identifies new values (endpoint_values - stored_values).
"""

import json
import logging
from typing import Any, Optional
from uuid import UUID

import httpx
from pydantic import Field, HttpUrl

from ada_backend.repositories.tracker_history_repository import seed_initial_endpoint_history
from ada_backend.services.cron.core import BaseExecutionPayload, BaseUserPayload, CronEntrySpec, get_cron_context
from ada_backend.services.cron.entries.agent_inference import AgentInferenceExecutionPayload, AgentInferenceUserPayload
from ada_backend.services.cron.entries.agent_inference import (
    validate_execution as validate_execution_agent_inference,
)
from ada_backend.services.cron.entries.agent_inference import (
    validate_registration as validate_registration_agent_inference,
)
from ada_backend.services.cron.errors import CronValidationError
from settings import settings

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
    track_history: bool = Field(
        default=True,
        description=(
            "Whether to save tracked values in history. "
            "If True (default), values are saved to prevent reprocessing. "
            "If False, the same values may be processed multiple times on each execution."
        ),
    )
    workflow_input: AgentInferenceUserPayload = Field(..., description="Agent inference input")
    workflow_input_template: Optional[str] = Field(
        default=None,
        description=(
            "Template for the workflow input message. Use {item} for the full item (JSON), "
            "or {item.key} to access specific fields (e.g., {item.name}, {item.step}). "
            "If None, defaults to just the item JSON."
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
                "track_history": True,
                "workflow_input": {
                    "project_id": "123e4567-e89b-12d3-a456-426614174000",
                    "env": "production",
                    "input_data": {
                        "messages": [
                            {"role": "user", "content": "Hello, run the daily report"},
                        ]
                    },
                },
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
    track_history: bool = True
    workflow_input: AgentInferenceExecutionPayload
    workflow_input_template: Optional[str] = None
    initial_history_seed: Optional[list[str]] = Field(default=None, exclude=True)


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
    agent_inference_execution_payload = validate_registration_agent_inference(
        user_input.workflow_input,
        organization_id=organization_id,
        user_id=user_id,
        **kwargs,
    )

    initial_tracked_values: set[str] = set()

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

        try:
            extracted_ids = _extract_ids_from_response(endpoint_data, user_input.tracking_field_path)
            initial_tracked_values = set(extracted_ids)
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

        if user_input.filter_fields:
            uses_array_notation = "[]" in user_input.tracking_field_path
            is_root_level_array = _is_root_level_array(endpoint_data)

            if not uses_array_notation and not is_root_level_array:
                raise CronValidationError(
                    "filter_fields can only be used when tracking_field_path "
                    "uses array notation (e.g., 'data[].id' or '[].id') or when "
                    f"the response is a root-level array, but got '{user_input.tracking_field_path}' "
                    f"and response is not an array."
                )

            effective_tracking_path, effective_filter_fields, filter_field_paths = _normalize_filter_paths(
                endpoint_data, user_input.tracking_field_path, user_input.filter_fields
            )

            if effective_tracking_path != user_input.tracking_field_path:
                LOGGER.info(
                    f"Auto-converting tracking_field_path '{user_input.tracking_field_path}' "
                    f"to '{effective_tracking_path}' for filter validation"
                )

            try:
                items_with_filter_values = _extract_ids_and_filter_values_from_response(
                    endpoint_data, effective_tracking_path, filter_field_paths
                )

                matching_ids = _filter_matching_items(items_with_filter_values, effective_filter_fields)
                initial_tracked_values = set(matching_ids)
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
        track_history=user_input.track_history,
        workflow_input=agent_inference_execution_payload,
        workflow_input_template=user_input.workflow_input_template,
        initial_history_seed=sorted(initial_tracked_values) if initial_tracked_values else None,
    )


def validate_execution(execution_payload: EndpointPollingExecutionPayload, **kwargs) -> None:
    """Validate execution payload and return None."""
    validate_execution_agent_inference(execution_payload.workflow_input, **kwargs)


def post_registration(execution_payload: EndpointPollingExecutionPayload, **kwargs) -> None:
    """
    Post-registration hook: seed history with existing endpoint values.

    This ensures the first execution only processes truly new values,
    not all values that existed when the cron was created.
    """
    cron_id, log_extra = get_cron_context(**kwargs)

    if not execution_payload.track_history:
        LOGGER.info("Skipping history seeding because track_history is False", extra=log_extra)
        return

    seed_values = execution_payload.initial_history_seed
    if not seed_values:
        return

    db = kwargs.get("db")
    if not db:
        raise ValueError("db missing from context")

    inserted = seed_initial_endpoint_history(db, cron_id, seed_values)
    if inserted:
        LOGGER.info(
            f"Seeded {inserted} existing endpoint values into history for cron {cron_id}",
            extra=log_extra
        )


async def execute(execution_payload: EndpointPollingExecutionPayload, **kwargs) -> dict[str, Any]:
    cron_id, log_extra = get_cron_context(**kwargs)

    if not settings.ADA_URL:
        raise ValueError("ADA_URL is not configured")
    if not settings.SCHEDULER_API_KEY:
        raise ValueError("SCHEDULER_API_KEY is not configured")

    url = f"{settings.ADA_URL}/internal/scheduler/endpoint-polling/run"

    LOGGER.info(
        f"Dispatching endpoint polling for cron_id={cron_id} "
        f"to {url}",
        extra=log_extra,
    )

    async with httpx.AsyncClient() as client:
        response = await client.post(
            url,
            json={"cron_id": str(cron_id), "payload": execution_payload.model_dump(mode="json")},
            headers={
                "X-Scheduler-API-Key": settings.SCHEDULER_API_KEY,
                "Content-Type": "application/json",
            },
        )
        response.raise_for_status()

    LOGGER.info(
        f"Endpoint polling dispatched for cron_id={cron_id}",
        extra=log_extra,
    )

    return {"status": "accepted", "cron_id": str(cron_id)}


spec = CronEntrySpec(
    user_payload_model=EndpointPollingUserPayload,
    execution_payload_model=EndpointPollingExecutionPayload,
    registration_validator=validate_registration,
    execution_validator=validate_execution,
    executor=execute,
    post_registration_hook=post_registration,
)


# ---------------------------------------------------------------------------
# Response extraction helpers (kept for validate_registration usage)
# ---------------------------------------------------------------------------


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


def _extract_field_value(item: Any, field_name: str) -> Any:
    """
    Extract a field value from an item (dict or object).

    If field_name is empty, returns the item itself.
    Returns None if the field doesn't exist.
    """
    if not field_name:
        return item

    if isinstance(item, dict):
        return item.get(field_name)
    elif hasattr(item, field_name):
        return getattr(item, field_name)
    return None


def _extract_ids_from_array(array: list[Any], field_name: str) -> set[str]:
    """Extract IDs from an array of items using a field name."""
    ids = set()
    for item in array:
        value = _extract_field_value(item, field_name)
        if value is not None:
            ids.add(str(value))
    return ids


def _is_root_level_array(data: Any) -> bool:
    """Check if data is a root-level array."""
    return isinstance(data, list) and len(data) > 0


def _parse_array_path(path: str) -> tuple[str, str]:
    """
    Parse array notation path into array_path and nested_field.

    Args:
        path: Path with array notation (e.g., 'data[].id' or '[].id')

    Returns:
        Tuple of (array_path, nested_field)
    """
    parts = path.split("[]")
    if len(parts) != 2:
        raise ValueError(f"Invalid field path format: {path}")
    return parts[0].rstrip("."), parts[1].lstrip(".")


def _get_array_from_path(data: Any, array_path: str, raise_on_error: bool = True) -> list[Any]:
    """
    Extract array from data using array path.

    Args:
        data: The data structure
        array_path: Path to the array (empty string for root-level)
        raise_on_error: Whether to raise ValueError on errors

    Returns:
        The array, or empty list if raise_on_error is False and path is invalid
    """
    if not array_path:
        if not isinstance(data, list):
            if raise_on_error:
                raise ValueError(f"Array path '{array_path}' (root) does not point to an array")
            return []
        return data

    array = _extract_nested_path(data, array_path)
    if array is None:
        if raise_on_error:
            raise ValueError(f"Array path '{array_path}' returned None")
        return []
    if not isinstance(array, list):
        if raise_on_error:
            raise ValueError(f"Path '{array_path}' does not point to an array")
        return []
    return array


def _normalize_filter_paths(
    data: Any, tracking_field_path: str, filter_fields: dict[str, str]
) -> tuple[str, dict[str, str], list[str]]:
    """
    Normalize tracking and filter field paths to array notation when needed.

    Args:
        data: The endpoint response data
        tracking_field_path: The tracking field path
        filter_fields: Dictionary of filter field paths to values

    Returns:
        Tuple of (effective_tracking_path, effective_filter_fields, filter_field_paths)
    """
    uses_array_notation = "[]" in tracking_field_path
    is_root_level_array = _is_root_level_array(data)

    effective_tracking_path = tracking_field_path
    if is_root_level_array and not uses_array_notation:
        effective_tracking_path = f"[].{tracking_field_path}"

    effective_filter_fields = {}
    filter_field_paths = []
    for filter_path, filter_value in filter_fields.items():
        if is_root_level_array and not uses_array_notation and "[]" not in filter_path:
            effective_filter_path = f"[].{filter_path}"
            effective_filter_fields[effective_filter_path] = filter_value
            filter_field_paths.append(effective_filter_path)
        else:
            effective_filter_fields[filter_path] = filter_value
            filter_field_paths.append(filter_path)

    return effective_tracking_path, effective_filter_fields, filter_field_paths


def _normalize_field_path(data: Any, field_path: str) -> tuple[str, bool]:
    """
    Normalize field path to array notation when needed.

    Returns:
        Tuple of (normalized_path, is_array_notation)
    """
    if "[]" in field_path:
        return field_path, True

    if _is_root_level_array(data):
        first_item = data[0]
        value = _extract_field_value(first_item, field_path)
        if value is not None:
            return f"[].{field_path}", True

    return field_path, False


def _extract_ids_from_response(data: Any, field_path: str) -> set[str]:
    """
    Extract IDs from API response using field path.

    Supports paths like:
    - "id" -> data["id"] or data.id
    - "data[].id" -> [item["id"] for item in data["data"]]
    - "items[].id" -> [item["id"] for item in data["items"]]
    - "[].id" -> [item["id"] for item in data] (when response is directly an array)
    """
    if not field_path:
        raise ValueError("field_path cannot be empty")

    normalized_path, is_array_notation = _normalize_field_path(data, field_path)

    if not is_array_notation:
        value = _extract_field_value(data, field_path)
        if value is None:
            raise ValueError(
                f"Field path '{field_path}' not found in response. "
                f"If the response is an array, use array notation like '[].{field_path}'"
            )
        return {str(value)}

    array_path, nested_field = _parse_array_path(normalized_path)
    array = _get_array_from_path(data, array_path)

    return _extract_ids_from_array(array, nested_field)


def _extract_items_with_ids_from_array(array: list[Any], id_field: str) -> dict[str, dict[str, Any]]:
    """Extract items from an array, mapping them by their ID field."""
    items_by_id: dict[str, dict[str, Any]] = {}
    for item in array:
        if isinstance(item, dict):
            value = _extract_field_value(item, id_field)
            if value is not None:
                item_id = str(value)
                if item_id:
                    items_by_id[item_id] = item
    return items_by_id


def _extract_items_with_ids(data: Any, tracking_field_path: str) -> dict[str, dict[str, Any]]:
    """
    Extract all items from response with their values.

    Returns a dictionary mapping item_value -> complete item.
    """
    normalized_path, is_array_notation = _normalize_field_path(data, tracking_field_path)

    if is_array_notation:
        try:
            array_path, id_field = _parse_array_path(normalized_path)
            array = _get_array_from_path(data, array_path, raise_on_error=False)
            if not array:
                return {}
            return _extract_items_with_ids_from_array(array, id_field)
        except ValueError:
            return {}

    if isinstance(data, dict) and tracking_field_path in data:
        value = data[tracking_field_path]
        item_id = str(value)
        if item_id:
            return {item_id: data}

    path_parts = tracking_field_path.split(".")
    if len(path_parts) > 1:
        parent_path = ".".join(path_parts[:-1])
        id_field = path_parts[-1]
        parent = _extract_nested_path(data, parent_path)
        if isinstance(parent, dict) and id_field in parent:
            value = parent[id_field]
            item_id = str(value)
            if item_id:
                return {item_id: parent}

    value = _extract_field_value(data, tracking_field_path)
    if value is not None:
        item_id = str(value)
        if item_id:
            return {item_id: data}

    return {}


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

    array_path, id_field = _parse_array_path(tracking_field_path)
    current = _get_array_from_path(data, array_path)

    filter_field_extractors = []
    for filter_field_path in filter_field_paths:
        try:
            _, filter_field = _parse_array_path(filter_field_path)
        except ValueError:
            filter_field = filter_field_path.lstrip(".")
        filter_field_extractors.append((filter_field_path, filter_field))

    result = {}
    for item in current:
        if isinstance(item, dict):
            id_value = _extract_field_value(item, id_field)
            if id_value is None:
                continue
            item_id = str(id_value)
            if not item_id:
                continue

            filter_values = {}
            for filter_field_path, filter_field in filter_field_extractors:
                value = _extract_field_value(item, filter_field)
                filter_values[filter_field_path] = str(value) if value is not None else None

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
