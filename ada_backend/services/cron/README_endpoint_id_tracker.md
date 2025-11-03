# Endpoint ID Tracker Cron Job

## Overview

The `endpoint_id_tracker` cron job monitors a GET endpoint and tracks new IDs that appear. When new IDs are detected, it can trigger workflows with the complete item data.

## Creating a Cron Job via API

### Endpoint

```
POST /organizations/{organization_id}/crons
```

### Request Body

```json
{
  "name": "My Endpoint Tracker",
  "cron_expr": "0 */5 * * *",
  "tz": "America/Santiago",
  "entrypoint": "endpoint_id_tracker",
  "payload": {
    "endpoint_url": "https://api.example.com/items",
    "id_field_path": "data[].id",
    "filter_fields": {
      "data[].status": "processing"
    },
    "headers": {
      "Authorization": "Bearer your-token-here"
    },
    "timeout": 30,
    "project_id": "123e4567-e89b-12d3-a456-426614174000",
    "env": "production",
    "workflow_input_template": "Process item: {item}"
  }
}
```

### Payload Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `endpoint_url` | string (URL) | Yes | GET endpoint URL to query for IDs |
| `id_field_path` | string | No (default: "id") | Path to the ID field in the response. Supports:<br>- `"id"` - Simple field<br>- `"data[].id"` - Array notation<br>- `"items[].id"` - Nested array |
| `filter_fields` | dict | No | Dictionary mapping filter field paths to target values. Only IDs matching all conditions will be tracked.<br>Example: `{"data[].status": "processing", "data[].priority": "high"}` |
| `headers` | dict | No | Optional HTTP headers for the request |
| `timeout` | int | No (default: 30) | Request timeout in seconds (1-300) |
| `project_id` | UUID | No | Project ID to trigger workflows for each new ID. If not provided, no workflows will be triggered |
| `env` | string | No (default: "production") | Environment for workflow execution: "draft" or "production" |
| `workflow_input_template` | string | No | Template for the workflow input message. Placeholders:<br>- `{id}` - The detected ID<br>- `{item}` - The full item as JSON string<br>If not provided, defaults to the item JSON or just the ID |

### Example with cURL

```bash
curl -X POST "https://your-api.com/organizations/123e4567-e89b-12d3-a456-426614174000/crons" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your-auth-token" \
  -d '{
    "name": "Monitor Processing Items",
    "cron_expr": "0 */5 * * *",
    "tz": "America/Santiago",
    "entrypoint": "endpoint_id_tracker",
    "payload": {
      "endpoint_url": "https://api.example.com/items",
      "id_field_path": "data[].id",
      "filter_fields": {
        "data[].status": "processing"
      },
      "headers": {
        "Authorization": "Bearer api-token"
      },
      "timeout": 30,
      "project_id": "123e4567-e89b-12d3-a456-426614174000",
      "env": "production",
      "workflow_input_template": "New item detected: {item}"
    }
  }'
```

### Example with Python requests

```python
import requests

url = "https://your-api.com/organizations/123e4567-e89b-12d3-a456-426614174000/crons"
headers = {
    "Content-Type": "application/json",
    "Authorization": "Bearer your-auth-token"
}
data = {
    "name": "Monitor Processing Items",
    "cron_expr": "0 */5 * * *",  # Every 5 minutes
    "tz": "America/Santiago",
    "entrypoint": "endpoint_id_tracker",
    "payload": {
        "endpoint_url": "https://api.example.com/items",
        "id_field_path": "data[].id",
        "filter_fields": {
            "data[].status": "processing"
        },
        "headers": {
            "Authorization": "Bearer api-token"
        },
        "timeout": 30,
        "project_id": "123e4567-e89b-12d3-a456-426614174000",
        "env": "production",
        "workflow_input_template": "New item detected: {item}"
    }
}

response = requests.post(url, json=data, headers=headers)
print(response.json())
```

## How It Works

1. **Extraction**: The cron job queries the endpoint and extracts all items using `id_field_path`
2. **Filtering**: If `filter_fields` is provided, only IDs matching all filter conditions are selected for tracking
3. **Tracking**: New IDs (not in the history) are saved to the database
4. **Workflow Triggering**: For each new ID, if `project_id` is provided, a workflow is triggered with:
   - The input message (from template or item JSON)
   - The complete item in `input_data["item"]` for easy access

## Cron Expression Examples

- `"0 */5 * * *"` - Every 5 minutes
- `"0 9 * * 1-5"` - Every weekday at 9 AM
- `"0 0 * * *"` - Daily at midnight
- `"*/10 * * * *"` - Every 10 minutes

## Notes

- The filtering (`filter_fields`) is only used for ID selection, not for workflow input
- Complete items are always passed to workflows, regardless of filtering
- IDs are tracked in the database; duplicates are prevented
- Only new IDs trigger workflows (IDs that weren't seen before)

