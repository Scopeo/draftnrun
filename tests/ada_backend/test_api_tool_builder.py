"""
Tests for API Tool Builder endpoints.
Ensures that tools are created uniquely, can be listed, updated, and deleted without duplicates.
"""

from uuid import uuid4
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient
import pytest
import sys

sys.modules["weasyprint"] = MagicMock()

from ada_backend.main import app  # noqa: E402
from ada_backend.scripts.get_supabase_token import get_user_jwt  # noqa: E402
from settings import settings  # noqa: E402

JWT_TOKEN = get_user_jwt(settings.TEST_USER_EMAIL, settings.TEST_USER_PASSWORD)
HEADERS_JWT = {
    "accept": "application/json",
    "Authorization": f"Bearer {JWT_TOKEN}",
}

# Store created tool IDs for cleanup
created_tool_ids = []


@pytest.fixture(autouse=True, scope="module")
def mock_super_admin_check():
    """Mock super-admin check for all tests in this module."""
    patcher = patch("ada_backend.routers.admin_tools_router.is_user_super_admin", new_callable=AsyncMock)
    mock = patcher.start()
    mock.return_value = True
    yield
    patcher.stop()


client = TestClient(app)


def test_create_api_tool():
    """Test creating a new API tool."""
    endpoint = "/admin-tools/api-tools"
    payload = {
        "tool_display_name": f"Test Weather API {uuid4()}",
        "endpoint": "https://api.weather.com/v1/forecast",
        "method": "GET",
        "headers": {
            "Authorization": "Bearer @{ENV:WEATHER_API_KEY}",
            "Content-Type": "application/json",
        },
        "timeout": 30,
        "fixed_parameters": {
            "units": "metric",
            "lang": "en",
        },
        "tool_description_name": f"weather_api_{uuid4().hex[:8]}",
        "tool_description": "Get weather forecast",
        "tool_properties": {
            "city": {
                "type": "string",
                "description": "City name",
            }
        },
        "required_tool_properties": ["city"],
    }

    response = client.post(endpoint, headers=HEADERS_JWT, json=payload)
    result = response.json()

    assert response.status_code == 200
    assert "component_instance_id" in result
    assert result["tool_display_name"] == payload["tool_display_name"]
    assert "tool_description_id" in result

    # Store for cleanup and further tests
    created_tool_ids.append(result["component_instance_id"])
    return result["component_instance_id"]


def test_create_multiple_tools_with_same_name():
    """Test that creating multiple tools with the same display name creates separate components."""
    endpoint = "/admin-tools/api-tools"
    tool_name = f"Duplicate Name Test {uuid4()}"

    payload1 = {
        "tool_display_name": tool_name,
        "endpoint": "https://api.example1.com",
        "method": "POST",
        "tool_description_name": f"dup_test_1_{uuid4().hex[:8]}",
        "tool_description": "First tool",
        "tool_properties": {},
        "required_tool_properties": [],
    }

    payload2 = {
        "tool_display_name": tool_name,
        "endpoint": "https://api.example2.com",
        "method": "GET",
        "tool_description_name": f"dup_test_2_{uuid4().hex[:8]}",
        "tool_description": "Second tool",
        "tool_properties": {},
        "required_tool_properties": [],
    }

    response1 = client.post(endpoint, headers=HEADERS_JWT, json=payload1)
    result1 = response1.json()
    assert response1.status_code == 200
    created_tool_ids.append(result1["component_instance_id"])

    response2 = client.post(endpoint, headers=HEADERS_JWT, json=payload2)
    result2 = response2.json()
    assert response2.status_code == 200
    created_tool_ids.append(result2["component_instance_id"])

    # Both should have different component_instance_ids
    assert result1["component_instance_id"] != result2["component_instance_id"]

    # List tools to ensure both appear separately
    list_response = client.get("/admin-tools/api-tools", headers=HEADERS_JWT)
    tools = list_response.json()["tools"]

    matching_tools = [t for t in tools if t["tool_display_name"] == tool_name]
    assert len(matching_tools) == 2, "Both tools with same name should appear in list"

    # Get details of both to ensure they have different endpoints
    detail1_response = client.get(f"/admin-tools/api-tools/{result1['component_instance_id']}", headers=HEADERS_JWT)
    detail1 = detail1_response.json()
    assert detail1["endpoint"] == "https://api.example1.com"

    detail2_response = client.get(f"/admin-tools/api-tools/{result2['component_instance_id']}", headers=HEADERS_JWT)
    detail2 = detail2_response.json()
    assert detail2["endpoint"] == "https://api.example2.com"


def test_list_api_tools():
    """Test listing all API tools."""
    # First create a tool to ensure list is not empty
    tool_id = test_create_api_tool()

    endpoint = "/admin-tools/api-tools"
    response = client.get(endpoint, headers=HEADERS_JWT)
    result = response.json()

    assert response.status_code == 200
    assert "tools" in result
    assert isinstance(result["tools"], list)
    assert len(result["tools"]) > 0

    # Verify structure of list items
    tool = result["tools"][0]
    assert "component_instance_id" in tool
    assert "tool_display_name" in tool
    assert "description" in tool
    assert "method" in tool
    assert "created_at" in tool
    assert "updated_at" in tool

    # Verify our created tool is in the list
    tool_ids = [t["component_instance_id"] for t in result["tools"]]
    assert tool_id in tool_ids


def test_get_api_tool_detail():
    """Test getting details of a specific API tool."""
    # Create a tool first
    tool_id = test_create_api_tool()

    endpoint = f"/admin-tools/api-tools/{tool_id}"
    response = client.get(endpoint, headers=HEADERS_JWT)
    result = response.json()

    assert response.status_code == 200
    assert result["component_instance_id"] == tool_id
    assert "tool_display_name" in result
    assert "endpoint" in result
    assert "method" in result
    assert "headers" in result
    assert "tool_description_name" in result
    assert "tool_description" in result
    assert "tool_properties" in result


def test_update_api_tool():
    """Test updating an existing API tool without creating duplicates."""
    # Create a tool first
    tool_id = test_create_api_tool()

    # Get initial count of tools
    list_response_before = client.get("/admin-tools/api-tools", headers=HEADERS_JWT)
    tools_before = list_response_before.json()["tools"]
    count_before = len(tools_before)

    # Get the tool description ID from the created tool
    detail_before_response = client.get(f"/admin-tools/api-tools/{tool_id}", headers=HEADERS_JWT)
    detail_before = detail_before_response.json()

    # Update the tool
    endpoint = f"/admin-tools/api-tools/{tool_id}"
    updated_payload = {
        "tool_display_name": f"Updated Test Weather API {uuid4()}",
        "endpoint": "https://api.weather.com/v2/forecast",
        "method": "POST",
        "headers": {
            "Authorization": "Bearer @{ENV:NEW_WEATHER_KEY}",
        },
        "timeout": 60,
        "fixed_parameters": {
            "units": "imperial",
        },
        "tool_description_id": detail_before["tool_description_id"],
        "tool_description_name": f"updated_weather_{uuid4().hex[:8]}",
        "tool_description": "Updated weather forecast",
        "tool_properties": {
            "location": {
                "type": "string",
                "description": "Location name",
            }
        },
        "required_tool_properties": ["location"],
    }

    response = client.put(endpoint, headers=HEADERS_JWT, json=updated_payload)
    result = response.json()

    assert response.status_code == 200
    assert result["component_instance_id"] == tool_id
    assert result["tool_display_name"] == updated_payload["tool_display_name"]

    # Get list again to ensure no duplicates were created
    list_response_after = client.get("/admin-tools/api-tools", headers=HEADERS_JWT)
    tools_after = list_response_after.json()["tools"]
    count_after = len(tools_after)

    assert count_after == count_before, "Update should not create duplicate tools"

    # Verify the tool was actually updated
    detail_response = client.get(f"/admin-tools/api-tools/{tool_id}", headers=HEADERS_JWT)
    detail = detail_response.json()

    assert detail["tool_display_name"] == updated_payload["tool_display_name"]
    assert detail["endpoint"] == updated_payload["endpoint"]
    assert detail["method"] == updated_payload["method"]
    assert detail["timeout"] == updated_payload["timeout"]


def test_update_api_tool_name_only():
    """Test that updating only the tool name doesn't affect other tools."""
    # Create two tools
    tool1_id = test_create_api_tool()
    tool2_id = test_create_api_tool()

    # Update first tool's name
    new_name = f"Renamed Tool {uuid4()}"
    endpoint = f"/admin-tools/api-tools/{tool1_id}"

    # Get original data
    detail_response = client.get(endpoint, headers=HEADERS_JWT)
    original_data = detail_response.json()

    # Update only the name
    update_payload = {
        "tool_display_name": new_name,
        "endpoint": original_data["endpoint"],
        "method": original_data["method"],
        "headers": original_data["headers"],
        "timeout": original_data["timeout"],
        "fixed_parameters": original_data["fixed_parameters"],
        "tool_description_id": original_data["tool_description_id"],
        "tool_description_name": original_data["tool_description_name"],
        "tool_description": original_data["tool_description"],
        "tool_properties": original_data["tool_properties"],
        "required_tool_properties": original_data["required_tool_properties"],
    }

    response = client.put(endpoint, headers=HEADERS_JWT, json=update_payload)
    assert response.status_code == 200

    # Verify first tool was updated
    detail1_response = client.get(f"/admin-tools/api-tools/{tool1_id}", headers=HEADERS_JWT)
    detail1 = detail1_response.json()
    assert detail1["tool_display_name"] == new_name

    # Verify second tool was NOT affected
    detail2_response = client.get(f"/admin-tools/api-tools/{tool2_id}", headers=HEADERS_JWT)
    detail2 = detail2_response.json()
    assert detail2["tool_display_name"] != new_name


def test_delete_api_tool():
    """Test deleting an API tool."""
    # Create a tool first
    tool_id = test_create_api_tool()

    # Get count before deletion
    list_response_before = client.get("/admin-tools/api-tools", headers=HEADERS_JWT)
    count_before = len(list_response_before.json()["tools"])

    # Delete the tool
    endpoint = f"/admin-tools/api-tools/{tool_id}"
    response = client.delete(endpoint, headers=HEADERS_JWT)

    assert response.status_code == 204

    # Verify it's removed from list
    list_response_after = client.get("/admin-tools/api-tools", headers=HEADERS_JWT)
    tools_after = list_response_after.json()["tools"]
    count_after = len(tools_after)

    assert count_after == count_before - 1

    # Verify it cannot be retrieved
    detail_response = client.get(f"/admin-tools/api-tools/{tool_id}", headers=HEADERS_JWT)
    assert detail_response.status_code == 404

    # Remove from cleanup list
    if tool_id in created_tool_ids:
        created_tool_ids.remove(tool_id)


def test_delete_one_tool_doesnt_affect_others():
    """Test that deleting one tool doesn't affect others with similar names."""
    # Create two tools
    tool1_id = test_create_api_tool()
    tool2_id = test_create_api_tool()

    # Get details of both before deletion
    detail2_before = client.get(f"/admin-tools/api-tools/{tool2_id}", headers=HEADERS_JWT).json()

    # Delete first tool
    delete_response = client.delete(f"/admin-tools/api-tools/{tool1_id}", headers=HEADERS_JWT)
    assert delete_response.status_code == 204

    # Verify second tool still exists and is unchanged
    detail2_after = client.get(f"/admin-tools/api-tools/{tool2_id}", headers=HEADERS_JWT)
    assert detail2_after.status_code == 200

    detail2_data = detail2_after.json()
    assert detail2_data["tool_display_name"] == detail2_before["tool_display_name"]
    assert detail2_data["endpoint"] == detail2_before["endpoint"]

    if tool1_id in created_tool_ids:
        created_tool_ids.remove(tool1_id)


def test_error_get_nonexistent_tool():
    """Test getting a tool that doesn't exist returns 404."""
    fake_id = str(uuid4())
    endpoint = f"/admin-tools/api-tools/{fake_id}"
    response = client.get(endpoint, headers=HEADERS_JWT)

    assert response.status_code == 404


def test_error_update_nonexistent_tool():
    """Test updating a tool that doesn't exist returns 400."""
    fake_id = str(uuid4())
    endpoint = f"/admin-tools/api-tools/{fake_id}"
    payload = {
        "tool_display_name": "Nonexistent Tool",
        "endpoint": "https://api.example.com",
        "method": "GET",
        "tool_description_name": "nonexistent_tool",
        "tool_description": "This doesn't exist",
        "tool_properties": {},
        "required_tool_properties": [],
    }

    response = client.put(endpoint, headers=HEADERS_JWT, json=payload)
    assert response.status_code == 400


def test_error_delete_nonexistent_tool():
    """Test deleting a tool that doesn't exist returns 404."""
    fake_id = str(uuid4())
    endpoint = f"/admin-tools/api-tools/{fake_id}"
    response = client.delete(endpoint, headers=HEADERS_JWT)

    assert response.status_code == 404


def test_cleanup_created_tools():
    """Cleanup any tools created during tests."""
    for tool_id in created_tool_ids[:]:
        try:
            client.delete(f"/admin-tools/api-tools/{tool_id}", headers=HEADERS_JWT)
            created_tool_ids.remove(tool_id)
        except Exception:
            pass
