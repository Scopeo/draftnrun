"""
Tests for tool description generator service.
"""

import uuid

from ada_backend.database import models as db
from ada_backend.services import tool_description_generator


def test_generate_tool_name():
    """Test tool name generation."""
    # Test with ref
    instance1 = db.ComponentInstance(id=uuid.uuid4(), ref="my_tool", name="My Tool")
    assert tool_description_generator.generate_tool_name(instance1) == "my_tool"

    # Test with name only
    instance2 = db.ComponentInstance(id=uuid.uuid4(), name="My Tool")
    assert tool_description_generator.generate_tool_name(instance2) == "My_Tool"

    # Test with ID only
    test_id = uuid.uuid4()
    instance3 = db.ComponentInstance(id=test_id)
    assert tool_description_generator.generate_tool_name(instance3) == f"tool_{test_id}"

    # Test name sanitization
    instance4 = db.ComponentInstance(id=uuid.uuid4(), ref="tool-with-special!@#chars")
    name = tool_description_generator.generate_tool_name(instance4)
    assert name == "tool_with_specialchars"


def test_generate_tool_description():
    """Test tool description generation."""
    # Test with name
    instance1 = db.ComponentInstance(id=uuid.uuid4(), name="My Tool", ref="my_tool")
    assert tool_description_generator.generate_tool_description(instance1) == "Tool: My Tool"

    # Test with ref only
    instance2 = db.ComponentInstance(id=uuid.uuid4(), ref="my_tool")
    assert tool_description_generator.generate_tool_description(instance2) == "Tool: my_tool"

    # Test with no name or ref
    instance3 = db.ComponentInstance(id=uuid.uuid4())
    assert tool_description_generator.generate_tool_description(instance3) == "A dynamically configured tool"
