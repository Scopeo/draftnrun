"""
Endpoint ID tracker cron entry: models, validators, executor, and spec.

This cron job queries a GET endpoint to fetch data with IDs,
compares them with existing IDs stored in the ingestion database,
and identifies new IDs (endpoint_ids - stored_ids).
"""

import logging
from typing import Any, Optional
from uuid import UUID
from datetime import datetime, timezone
from pydantic import Field, HttpUrl

import httpx

from ada_backend.services.cron.core import BaseUserPayload, BaseExecutionPayload, CronEntrySpec
from ada_backend.repositories.project_repository import get_project
from ada_backend.services.agent_runner_service import run_env_agent
from ada_backend.database.models import CallType, EnvType
from ingestion_script.utils import get_sanitize_names
from engine.storage_service.local_service import SQLLocalService
from engine.storage_service.db_utils import DBDefinition, DBColumn, PROCESSED_DATETIME_FIELD
from settings import settings

LOGGER = logging.getLogger(__name__)


class EndpointIdTrackerUserPayload(BaseUserPayload):
    """User input for endpoint ID tracker cron jobs."""

    endpoint_url: HttpUrl = Field(..., description="GET endpoint URL to query for IDs")
    id_field_path: str = Field(
        default="id",
        description="Path to the ID field in the response (e.g., 'id', 'data[].id', 'items[].id')",
    )
    filter_fields: Optional[dict[str, str]] = Field(
        default=None,
        description="Dictionary mapping filter field paths to their target values (e.g., {'data[].status': 'processing', 'data[].priority': 'high'}). Only IDs matching all filter conditions will be tracked.",
    )
    headers: Optional[dict[str, str]] = Field(default=None, description="Optional HTTP headers for the request")
    timeout: int = Field(default=30, ge=1, le=300, description="Request timeout in seconds")
    project_id: Optional[UUID] = Field(
        default=None,
        description="Project ID to trigger workflows for each new ID detected. If None, no workflows will be triggered.",
    )
    env: EnvType = Field(
        default=EnvType.PRODUCTION,
        description="Environment (draft/production) for workflow execution",
    )
    workflow_input_template: Optional[str] = Field(
        default=None,
        description="Template for the workflow input message. Use {id} as placeholder for the detected ID. If None, defaults to just the ID string.",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "endpoint_url": "https://api.example.com/items",
                "id_field_path": "data[].id",
                "filter_fields": {"data[].status": "processing"},
                "headers": {"Authorization": "Bearer token"},
                "timeout": 30,
                "project_id": "123e4567-e89b-12d3-a456-426614174000",
                "env": "production",
                "workflow_input_template": "Process item with ID {id}",
            }
        }


class EndpointIdTrackerExecutionPayload(BaseExecutionPayload):
    """Execution payload stored in database for endpoint ID tracker jobs."""

    endpoint_url: str
    id_field_path: str
    filter_fields: Optional[dict[str, str]] = None
    headers: Optional[dict[str, str]]
    timeout: int
    organization_id: UUID
    created_by: UUID
    project_id: Optional[UUID] = None
    env: EnvType = EnvType.PRODUCTION
    workflow_input_template: Optional[str] = None


def validate_registration(
    user_input: EndpointIdTrackerUserPayload, organization_id: UUID, user_id: UUID, **kwargs
) -> EndpointIdTrackerExecutionPayload:
    """
    Validate user input and return the execution payload
    that will be used to execute the job.
    Table names are generated dynamically using organization_id and cron_id during execution.
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

    return EndpointIdTrackerExecutionPayload(
        endpoint_url=str(user_input.endpoint_url),
        id_field_path=user_input.id_field_path,
        filter_fields=user_input.filter_fields,
        headers=user_input.headers,
        timeout=user_input.timeout,
        organization_id=organization_id,
        created_by=user_id,
        project_id=user_input.project_id,
        env=user_input.env,
        workflow_input_template=user_input.workflow_input_template,
    )


def validate_execution(execution_payload: EndpointIdTrackerExecutionPayload, **kwargs) -> None:
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
    Used only for filtering - filter_values are not saved to DB.

    Args:
        data: The API response data
        id_field_path: Path to the ID field (e.g., 'data[].id')
        filter_field_paths: List of paths to filter fields (e.g., ['data[].status', 'data[].priority'])

    Returns:
        Dictionary mapping ID to a dict containing all filter values.
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
            }

    return result


async def execute(execution_payload: EndpointIdTrackerExecutionPayload, **kwargs) -> dict[str, Any]:
    db = kwargs.get("db")
    if not db:
        raise ValueError("db missing from context")

    cron_id = kwargs.get("cron_id")
    if not cron_id:
        raise ValueError("cron_id is required for table naming")

    LOGGER.info(f"Starting endpoint ID tracker for endpoint {execution_payload.endpoint_url}")

    # Generate table names dynamically using organization_id and cron_id
    # This matches how tables are saved in the ingestion database
    schema_name, table_name, _ = get_sanitize_names(str(execution_payload.organization_id), str(cron_id))

    # Step 1: Query the endpoint
    LOGGER.info(f"Querying endpoint: {execution_payload.endpoint_url}")
    async with httpx.AsyncClient(timeout=execution_payload.timeout) as client:
        response = await client.get(
            execution_payload.endpoint_url,
            headers=execution_payload.headers,
        )
        response.raise_for_status()
        endpoint_data = response.json()

    # Step 2: Extract IDs from the response (with filtering if filter_fields provided)
    filter_fields = execution_payload.filter_fields
    if filter_fields:
        filter_field_paths = list(filter_fields.keys())
        items_with_filter_values = _extract_ids_and_filter_values_from_response(
            endpoint_data, execution_payload.id_field_path, filter_field_paths
        )

        endpoint_ids = set()
        for item_id, item_data in items_with_filter_values.items():
            filter_values = item_data.get("filter_values", {})
            matches_all = all(
                filter_values.get(field_path) == target_value for field_path, target_value in filter_fields.items()
            )
            if matches_all:
                endpoint_ids.add(item_id)

        LOGGER.info(
            f"Found {len(endpoint_ids)} IDs matching filter conditions out of {len(items_with_filter_values)} total IDs"
        )
    else:
        endpoint_ids = _extract_ids_from_response(endpoint_data, execution_payload.id_field_path)
        LOGGER.info(f"Found {len(endpoint_ids)} IDs from endpoint")

    # Step 3: Ensure simple tracking table exists and get existing data
    if not settings.INGESTION_DB_URL:
        raise ValueError("INGESTION_DB_URL is not configured")

    db_service = SQLLocalService(engine_url=settings.INGESTION_DB_URL)

    # Simple table: just track processed IDs
    table_definition = DBDefinition(
        columns=[
            DBColumn(name=PROCESSED_DATETIME_FIELD, type="DATETIME", default="CURRENT_TIMESTAMP"),
            DBColumn(name="id", type="VARCHAR", is_primary=True),
            DBColumn(name="created_at", type="TIMESTAMP", default="CURRENT_TIMESTAMP"),
            DBColumn(name="updated_at", type="TIMESTAMP", default="CURRENT_TIMESTAMP"),
        ]
    )

    if not db_service.schema_exists(schema_name):
        db_service.create_schema(schema_name)

    if not db_service.table_exists(table_name, schema_name):
        db_service.create_table(
            table_name=table_name,
            table_definition=table_definition,
            schema_name=schema_name,
        )
        LOGGER.info(f"Created tracking table {table_name} in schema {schema_name}")

    try:
        df = db_service.get_table_df(
            table_name=table_name,
            schema_name=schema_name,
        )

        # Simple: just get the list of already processed IDs
        if df.empty:
            stored_ids = set()
        else:
            stored_ids = set(df["id"].astype(str).unique())

        LOGGER.info(f"Found {len(stored_ids)} already processed IDs")
    except Exception as e:
        LOGGER.warning(f"Error querying tracking table: {e}, starting with empty state")
        stored_ids = set()

    # Step 4: Identify new IDs and save processed ones
    current_time = datetime.now(timezone.utc)
    new_ids = endpoint_ids - stored_ids
    removed_ids = stored_ids - endpoint_ids

    # Save all current IDs as processed (upsert)
    for item_id in endpoint_ids:
        is_new = item_id not in stored_ids
        values = {
            "updated_at": current_time,
        }
        if is_new:
            values["created_at"] = current_time
        db_service.upsert_value(
            table_name=table_name,
            id_column_name="id",
            id=str(item_id),
            values=values,
            schema_name=schema_name,
        )

    # Remove IDs that are no longer in endpoint (batch delete)
    if removed_ids:
        db_service.delete_rows_from_table(
            table_name=table_name,
            ids=[str(rid) for rid in removed_ids],
            schema_name=schema_name,
            id_column_name="id",
        )

    LOGGER.info(f"Identified {len(new_ids)} new IDs and {len(removed_ids)} removed IDs")

    # Trigger workflows for new IDs if project_id is configured
    workflow_results = []
    if execution_payload.project_id and new_ids:
        LOGGER.info(f"Triggering workflows for {len(new_ids)} new IDs in project {execution_payload.project_id}")
        for new_id in new_ids:
            try:
                # Create input message using template or default to ID
                if execution_payload.workflow_input_template:
                    input_message = execution_payload.workflow_input_template.format(id=new_id)
                else:
                    input_message = str(new_id)

                # Create input data with the customized message
                input_data = {
                    "messages": [
                        {"role": "user", "content": input_message},
                    ]
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
                        "id": new_id,
                        "status": "success",
                        "message": workflow_result.message,
                        "trace_id": workflow_result.trace_id,
                    }
                )
                LOGGER.info(f"Successfully triggered workflow for ID {new_id} with message: {input_message}")
            except Exception as e:
                LOGGER.error(f"Failed to trigger workflow for ID {new_id}: {e}")
                workflow_results.append(
                    {
                        "id": new_id,
                        "status": "error",
                        "error": str(e),
                    }
                )

    return {
        "endpoint_url": execution_payload.endpoint_url,
        "schema_name": schema_name,
        "table_name": table_name,
        "total_endpoint_ids": len(endpoint_ids),
        "total_stored_ids": len(stored_ids),
        "new_ids_count": len(new_ids),
        "removed_ids_count": len(removed_ids),
        "new_ids": sorted(list(new_ids)) if new_ids else [],
        "removed_ids": sorted(list(removed_ids)) if removed_ids else [],
        "workflows_triggered": workflow_results,
    }


spec = CronEntrySpec(
    user_payload_model=EndpointIdTrackerUserPayload,
    execution_payload_model=EndpointIdTrackerExecutionPayload,
    registration_validator=validate_registration,
    execution_validator=validate_execution,
    executor=execute,
)
