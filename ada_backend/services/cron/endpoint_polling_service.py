"""
Endpoint polling business logic: fetch, diff, and trigger.

This module contains the core execution logic for endpoint polling cron jobs.
It is intentionally decoupled from the scheduler entry so the scheduler remains
a thin HTTP dispatcher.
"""

from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING, Any
from uuid import UUID

import httpx
from sqlalchemy.orm import Session

from ada_backend.repositories.tracker_history_repository import (
    create_tracked_values_bulk,
    get_tracked_values_history,
)

if TYPE_CHECKING:
    from ada_backend.services.cron.entries.endpoint_polling import EndpointPollingExecutionPayload

LOGGER = logging.getLogger(__name__)


def format_workflow_template(template: str, item: dict[str, Any]) -> str:
    """
    Format workflow input template with support for:
    - {item} - the full item as JSON string
    - {item.key} - access nested fields from the item (e.g., {item.name}, {item.step})
    """
    result = template

    item_pattern = r"\{item\.([^}]+)\}"

    def replace_item_field(match):
        field_path = match.group(1)
        try:
            value = item
            for key in field_path.split("."):
                if isinstance(value, dict):
                    value = value.get(key)
                elif hasattr(value, key):
                    value = getattr(value, key)
                else:
                    return ""
                if value is None:
                    return ""
            return str(value)
        except (AttributeError, KeyError, TypeError):
            return ""

    result = re.sub(item_pattern, replace_item_field, result)

    item_json = json.dumps(item, default=str) if item else "{}"
    result = result.replace("{item}", item_json)

    return result


def _extract_nested_path(data: Any, path: str) -> Any:
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
    if not field_name:
        return item
    if isinstance(item, dict):
        return item.get(field_name)
    elif hasattr(item, field_name):
        return getattr(item, field_name)
    return None


def _extract_ids_from_array(array: list[Any], field_name: str) -> set[str]:
    ids = set()
    for item in array:
        value = _extract_field_value(item, field_name)
        if value is not None:
            ids.add(str(value))
    return ids


def _is_root_level_array(data: Any) -> bool:
    return isinstance(data, list) and len(data) > 0


def _parse_array_path(path: str) -> tuple[str, str]:
    parts = path.split("[]")
    if len(parts) != 2:
        raise ValueError(f"Invalid field path format: {path}")
    return parts[0].rstrip("."), parts[1].lstrip(".")


def _get_array_from_path(data: Any, array_path: str, raise_on_error: bool = True) -> list[Any]:
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
    if "[]" in field_path:
        return field_path, True

    if _is_root_level_array(data):
        first_item = data[0]
        value = _extract_field_value(first_item, field_path)
        if value is not None:
            return f"[].{field_path}", True

    return field_path, False


def _extract_ids_from_response(data: Any, field_path: str) -> set[str]:
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
                "item": item,
            }

    return result


def _filter_matching_items(
    items_with_filter_values: dict[str, dict[str, Any]], filter_fields: dict[str, str]
) -> set[str]:
    matching_ids = set()
    for item_id, item_data in items_with_filter_values.items():
        filter_values = item_data.get("filter_values", {})
        matches_all = all(
            filter_values.get(field_path) == target_value for field_path, target_value in filter_fields.items()
        )
        if matches_all:
            matching_ids.add(item_id)
    return matching_ids


# ---------------------------------------------------------------------------
# Core execution logic
# ---------------------------------------------------------------------------


async def run_endpoint_polling(
    cron_id: UUID,
    payload: EndpointPollingExecutionPayload,
    db: Session,
    ada_url: str,
    scheduler_api_key: str,
) -> dict[str, Any]:
    """
    Full poll → diff → trigger loop for an endpoint polling cron job.

    Fetches the external endpoint, identifies new values relative to stored
    history, triggers a workflow run per new value, and persists successful
    values back to history.
    """
    log_extra = {"cron_id": str(cron_id)}

    LOGGER.info(f"Starting endpoint polling for endpoint {payload.endpoint_url}", extra=log_extra)

    async with httpx.AsyncClient(timeout=payload.timeout) as client:
        response = await client.get(payload.endpoint_url, headers=payload.headers)
        response.raise_for_status()
        endpoint_data = response.json()

    items_by_id = _extract_items_with_ids(endpoint_data, payload.tracking_field_path)

    filter_fields = payload.filter_fields
    if filter_fields:
        effective_tracking_path, effective_filter_fields, filter_field_paths = _normalize_filter_paths(
            endpoint_data, payload.tracking_field_path, filter_fields
        )
        items_with_filter_values = _extract_ids_and_filter_values_from_response(
            endpoint_data, effective_tracking_path, filter_field_paths
        )
        polled_values = _filter_matching_items(items_with_filter_values, effective_filter_fields)
        LOGGER.info(
            f"Found {len(polled_values)} values matching filter "
            f"conditions out of {len(items_with_filter_values)} total values",
            extra=log_extra,
        )
    else:
        polled_values = _extract_ids_from_response(endpoint_data, payload.tracking_field_path)
        LOGGER.info(f"Found {len(polled_values)} values from endpoint", extra=log_extra)

    if payload.track_history:
        stored_history = get_tracked_values_history(db, cron_id)
        stored_ids = {str(record.tracked_value) for record in stored_history}
        LOGGER.info(f"Found {len(stored_ids)} already processed values", extra=log_extra)
        new_values = polled_values - stored_ids
        LOGGER.info(f"Identified {len(new_values)} new values", extra=log_extra)
    else:
        stored_ids = set()
        new_values = polled_values
        LOGGER.info(f"History tracking disabled - processing all {len(new_values)} polled values", extra=log_extra)

    workflow_results = []
    successful_values = []
    agent_payload = payload.workflow_input

    if agent_payload.project_id and new_values:
        LOGGER.info(
            f"Triggering workflows for {len(new_values)} new values in project {agent_payload.project_id}",
            extra=log_extra,
        )
        run_url = f"{ada_url}/internal/webhooks/projects/{agent_payload.project_id}/envs/{agent_payload.env}/run"
        async with httpx.AsyncClient() as client:
            for new_value in new_values:
                try:
                    item = items_by_id.get(new_value, {})
                    if payload.workflow_input_template:
                        input_message = format_workflow_template(payload.workflow_input_template, item)
                    else:
                        input_message = json.dumps(item, default=str) if item else str(new_value)

                    body = {
                        "input_data": {
                            "messages": [{"role": "user", "content": input_message}],
                            "item": item,
                        },
                    }
                    resp = await client.post(
                        run_url,
                        json=body,
                        headers={
                            "X-Scheduler-API-Key": scheduler_api_key,
                            "Content-Type": "application/json",
                        },
                    )
                    resp.raise_for_status()
                    workflow_results.append({"id": new_value, "status": "accepted"})
                    successful_values.append(new_value)
                    LOGGER.info(f"Successfully triggered workflow for value {new_value}", extra=log_extra)
                except Exception as e:
                    LOGGER.error(f"Failed to trigger workflow for value {new_value}: {e}", extra=log_extra)
                    workflow_results.append({"id": new_value, "status": "error", "error": str(e)})

    if successful_values and payload.track_history:
        create_tracked_values_bulk(session=db, cron_id=cron_id, tracked_values=successful_values)
        LOGGER.info(f"Added {len(successful_values)} successfully processed values to history", extra=log_extra)
    elif successful_values and not payload.track_history:
        LOGGER.info(
            f"Processed {len(successful_values)} values (not saved to history - track_history is False)",
            extra=log_extra,
        )

    return {
        "endpoint_url": payload.endpoint_url,
        "total_polled_values": len(polled_values),
        "total_stored_ids": len(stored_ids),
        "new_values_count": len(new_values),
        "new_values": sorted(list(new_values)) if new_values else [],
        "workflows_triggered": workflow_results,
    }
