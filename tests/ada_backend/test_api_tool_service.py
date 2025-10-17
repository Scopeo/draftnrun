"""Unit tests for API Tool Management service layer."""

from uuid import uuid4

import pytest

from ada_backend.database import models as db
from ada_backend.services.admin_tools_service import (
    create_specific_api_tool_service,
    list_api_tools_service,
    get_api_tool_detail_service,
    update_api_tool_service,
    delete_api_tool_service,
)
from ada_backend.schemas.admin_tools_schema import CreateSpecificApiToolRequest


@pytest.fixture
def sample_tool_payload():
    """Create a sample API tool payload for testing."""
    unique_suffix = uuid4().hex[:8]
    return CreateSpecificApiToolRequest(
        tool_display_name=f"Test API Tool {unique_suffix}",
        endpoint="https://api.test.com/v1/endpoint",
        method="POST",
        headers={"Authorization": "Bearer @{ENV:TEST_KEY}"},
        timeout=45,
        fixed_parameters={"version": "v1"},
        tool_description_name=f"test_tool_{unique_suffix}",
        tool_description="Test tool description",
        tool_properties={"param1": {"type": "string"}},
        required_tool_properties=["param1"],
    )


@pytest.fixture
def clean_test_session(test_db):
    """
    Provides a clean SQLAlchemy session without seeding.
    API tool service tests create their own test data.
    """
    engine, SessionLocal = test_db
    connection = engine.connect()
    transaction = connection.begin()
    _session = SessionLocal(bind=connection)

    yield _session

    _session.close()
    transaction.rollback()
    connection.close()


def test_create_tool_creates_unique_component(clean_test_session, sample_tool_payload):
    """Test that creating a tool creates a unique component."""
    # Create first tool
    result1 = create_specific_api_tool_service(clean_test_session, sample_tool_payload)

    assert result1.component_instance_id is not None
    assert result1.tool_display_name == sample_tool_payload.tool_display_name

    # Create second tool with same display name but different tool_description_name
    unique_suffix2 = uuid4().hex[:8]
    sample_tool_payload.tool_description_name = f"test_tool_{unique_suffix2}"
    result2 = create_specific_api_tool_service(clean_test_session, sample_tool_payload)

    assert result2.component_instance_id is not None
    assert result2.component_instance_id != result1.component_instance_id

    # List tools to verify both exist
    tools_list = list_api_tools_service(clean_test_session)
    matching_tools = [t for t in tools_list.tools if t.tool_display_name == sample_tool_payload.tool_display_name]

    assert len(matching_tools) == 2, "Both tools should exist independently"


def test_list_tools_excludes_base_component(clean_test_session, sample_tool_payload):
    """Test that list excludes the base 'API Call' component."""
    # Create a tool
    create_specific_api_tool_service(clean_test_session, sample_tool_payload)

    # List tools
    tools_list = list_api_tools_service(clean_test_session)

    # Verify no tool is named 'API Call' (the base component)
    api_call_tools = [t for t in tools_list.tools if t.tool_display_name == "API Call"]
    assert len(api_call_tools) == 0, "Base 'API Call' component should be excluded"


def test_get_tool_detail_returns_complete_data(clean_test_session, sample_tool_payload):
    """Test that getting tool details returns all necessary fields."""
    # Create a tool
    created = create_specific_api_tool_service(clean_test_session, sample_tool_payload)

    # Get details
    detail = get_api_tool_detail_service(clean_test_session, created.component_instance_id)

    assert detail.component_instance_id == created.component_instance_id
    assert detail.tool_display_name == sample_tool_payload.tool_display_name
    assert detail.endpoint == sample_tool_payload.endpoint
    assert detail.method == sample_tool_payload.method
    assert detail.headers == sample_tool_payload.headers
    assert detail.timeout == sample_tool_payload.timeout
    assert detail.fixed_parameters == sample_tool_payload.fixed_parameters
    assert detail.tool_description_name == sample_tool_payload.tool_description_name
    assert detail.tool_description == sample_tool_payload.tool_description


def test_update_tool_modifies_existing_not_creates_new(clean_test_session, sample_tool_payload):
    """Test that updating a tool modifies existing records, not create new ones."""
    # Create a tool
    created = create_specific_api_tool_service(clean_test_session, sample_tool_payload)

    # Get count before update
    list_before = list_api_tools_service(clean_test_session)
    count_before = len(list_before.tools)

    # Get the tool description ID from the created tool
    detail_before = get_api_tool_detail_service(clean_test_session, created.component_instance_id)

    # Update the tool
    updated_payload = CreateSpecificApiToolRequest(
        tool_display_name=f"Updated {sample_tool_payload.tool_display_name}",
        endpoint="https://api.test.com/v2/endpoint",
        method="GET",
        headers={"Authorization": "Bearer @{ENV:NEW_KEY}"},
        timeout=60,
        fixed_parameters={"version": "v2"},
        tool_description_id=detail_before.tool_description_id,
        tool_description_name=sample_tool_payload.tool_description_name,
        tool_description="Updated description",
        tool_properties={"new_param": {"type": "integer"}},
        required_tool_properties=["new_param"],
    )

    updated = update_api_tool_service(clean_test_session, created.component_instance_id, updated_payload)

    assert updated.component_instance_id == created.component_instance_id

    # Get count after update
    list_after = list_api_tools_service(clean_test_session)
    count_after = len(list_after.tools)

    assert count_after == count_before, "Update should not create new tools"

    # Verify the tool was actually updated
    detail = get_api_tool_detail_service(clean_test_session, created.component_instance_id)
    assert detail.tool_display_name == updated_payload.tool_display_name
    assert detail.endpoint == updated_payload.endpoint
    assert detail.method == updated_payload.method


def test_update_one_tool_doesnt_affect_others(clean_test_session, sample_tool_payload):
    """Test that updating one tool doesn't affect other tools."""
    # Create two tools
    created1 = create_specific_api_tool_service(clean_test_session, sample_tool_payload)

    payload2 = CreateSpecificApiToolRequest(
        tool_display_name=f"Another Tool {uuid4().hex[:8]}",
        endpoint="https://api.another.com",
        method="GET",
        tool_description_name=f"another_tool_{uuid4().hex[:8]}",
        tool_description="Another tool",
        tool_properties={},
        required_tool_properties=[],
    )
    created2 = create_specific_api_tool_service(clean_test_session, payload2)

    # Get details of both tools before update
    detail1_before = get_api_tool_detail_service(clean_test_session, created1.component_instance_id)
    detail2_before = get_api_tool_detail_service(clean_test_session, created2.component_instance_id)

    # Update first tool
    updated_payload = CreateSpecificApiToolRequest(
        tool_display_name="Completely Different Name",
        endpoint="https://api.different.com",
        method="PUT",
        tool_description_id=detail1_before.tool_description_id,
        tool_description_name=sample_tool_payload.tool_description_name,
        tool_description="Different description",
        tool_properties={},
        required_tool_properties=[],
    )

    update_api_tool_service(clean_test_session, created1.component_instance_id, updated_payload)

    # Get details of second tool after update
    detail2_after = get_api_tool_detail_service(clean_test_session, created2.component_instance_id)

    # Verify second tool is unchanged
    assert detail2_after.tool_display_name == detail2_before.tool_display_name
    assert detail2_after.endpoint == detail2_before.endpoint
    assert detail2_after.method == detail2_before.method


def test_delete_tool_removes_from_list(clean_test_session, sample_tool_payload):
    """Test that deleting a tool removes it from the list."""
    # Create a tool
    created = create_specific_api_tool_service(clean_test_session, sample_tool_payload)

    # Verify it's in the list
    list_before = list_api_tools_service(clean_test_session)
    ids_before = [t.component_instance_id for t in list_before.tools]
    assert created.component_instance_id in ids_before

    # Delete the tool
    delete_api_tool_service(clean_test_session, created.component_instance_id)

    # Verify it's removed from the list
    list_after = list_api_tools_service(clean_test_session)
    ids_after = [t.component_instance_id for t in list_after.tools]
    assert created.component_instance_id not in ids_after


def test_delete_tool_raises_error_if_not_found(clean_test_session):
    """Test that deleting a nonexistent tool raises an error."""
    fake_id = uuid4()

    with pytest.raises(ValueError, match="not found"):
        delete_api_tool_service(clean_test_session, fake_id)


def test_get_tool_detail_raises_error_if_not_found(clean_test_session):
    """Test that getting details of a nonexistent tool raises an error."""
    fake_id = uuid4()

    with pytest.raises(ValueError, match="not found"):
        get_api_tool_detail_service(clean_test_session, fake_id)


def test_update_tool_raises_error_if_not_found(clean_test_session, sample_tool_payload):
    """Test that updating a nonexistent tool raises an error."""
    fake_id = uuid4()

    with pytest.raises(ValueError, match="not found"):
        update_api_tool_service(clean_test_session, fake_id, sample_tool_payload)


def test_tool_properties_serialization(clean_test_session):
    """Test that tool properties with complex JSON are properly serialized."""
    payload = CreateSpecificApiToolRequest(
        tool_display_name=f"Complex Tool {uuid4().hex[:8]}",
        endpoint="https://api.complex.com",
        method="POST",
        headers={
            "Authorization": "Bearer token",
            "X-Custom-Header": "value",
        },
        fixed_parameters={
            "nested": {"key": "value"},
            "array": ["item1", "item2"],
        },
        tool_description_name=f"complex_tool_{uuid4().hex[:8]}",
        tool_description="Complex tool",
        tool_properties={"complex_param": {"type": "object", "properties": {"sub_param": {"type": "string"}}}},
        required_tool_properties=["complex_param"],
    )

    created = create_specific_api_tool_service(clean_test_session, payload)
    detail = get_api_tool_detail_service(clean_test_session, created.component_instance_id)

    # Verify complex structures are preserved
    assert detail.headers == payload.headers
    assert detail.fixed_parameters == payload.fixed_parameters
    assert detail.tool_properties == payload.tool_properties


def test_update_tool_requires_tool_description_id(clean_test_session, sample_tool_payload):
    created = create_specific_api_tool_service(clean_test_session, sample_tool_payload)

    with pytest.raises(ValueError, match="tool_description_id is required"):
        update_api_tool_service(clean_test_session, created.component_instance_id, sample_tool_payload)


def test_update_tool_with_shared_component_creates_clone(clean_test_session, sample_tool_payload):
    created = create_specific_api_tool_service(clean_test_session, sample_tool_payload)
    detail_before = get_api_tool_detail_service(clean_test_session, created.component_instance_id)

    legacy_instance = db.ComponentInstance(
        id=uuid4(),
        component_id=detail_before.component_id,
        name="Legacy Shared Tool",
        tool_description_id=detail_before.tool_description_id,
    )
    clean_test_session.add(legacy_instance)
    clean_test_session.commit()

    updated_payload = CreateSpecificApiToolRequest(
        tool_display_name="Updated Shared Tool",
        endpoint="https://api.updated.com",
        method="PATCH",
        headers={"Authorization": "Bearer @{ENV:UPDATED}"},
        timeout=75,
        fixed_parameters={"version": "v3"},
        tool_description_id=detail_before.tool_description_id,
        tool_description_name=sample_tool_payload.tool_description_name,
        tool_description="Updated description",
        tool_properties={"foo": {"type": "string"}},
        required_tool_properties=["foo"],
    )

    update_api_tool_service(clean_test_session, created.component_instance_id, updated_payload)

    detail_after = get_api_tool_detail_service(clean_test_session, created.component_instance_id)
    assert detail_after.component_id != detail_before.component_id

    refreshed_legacy = (
        clean_test_session.query(db.ComponentInstance).filter(db.ComponentInstance.id == legacy_instance.id).one()
    )
    assert refreshed_legacy.component_id == detail_before.component_id


def test_delete_tool_with_shared_component_only_removes_instance(clean_test_session, sample_tool_payload):
    created = create_specific_api_tool_service(clean_test_session, sample_tool_payload)
    detail = get_api_tool_detail_service(clean_test_session, created.component_instance_id)

    shared_instance = db.ComponentInstance(
        id=uuid4(),
        component_id=detail.component_id,
        name="Shared Tool",
        tool_description_id=detail.tool_description_id,
    )
    clean_test_session.add(shared_instance)
    clean_test_session.commit()

    delete_api_tool_service(clean_test_session, shared_instance.id)

    remaining_instance = (
        clean_test_session.query(db.ComponentInstance)
        .filter(db.ComponentInstance.id == created.component_instance_id)
        .one_or_none()
    )
    assert remaining_instance is not None

    component_still_exists = (
        clean_test_session.query(db.Component).filter(db.Component.id == detail.component_id).one_or_none()
    )
    assert component_still_exists is not None
