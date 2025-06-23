import pytest
import json
import os
from unittest.mock import MagicMock

from engine.agent.tools.python_code_interpreter_e2b_tool import (
    PythonCodeInterpreterE2BTool,
    E2B_PYTHONCODE_INTERPRETER_TOOL_DESCRIPTION,
)
from engine.agent.agent import AgentPayload, ChatMessage
from engine.trace.trace_manager import TraceManager


@pytest.fixture
def mock_trace_manager():
    return MagicMock(spec=TraceManager)


@pytest.fixture
def e2b_tool(mock_trace_manager):
    """Create an E2B Python code interpreter tool instance."""
    return PythonCodeInterpreterE2BTool(
        trace_manager=mock_trace_manager,
        component_instance_name="test_e2b_tool",
        sandbox_timeout=30,
    )


@pytest.fixture
def e2b_api_key():
    """Get E2B API key from environment or skip test if not available."""
    api_key = os.getenv("E2B_API_KEY")
    if not api_key:
        pytest.skip("E2B_API_KEY environment variable not set")
    return api_key


def test_tool_initialization(e2b_tool):
    """Test that the tool initializes correctly."""
    assert e2b_tool.component_instance_name == "test_e2b_tool"
    assert e2b_tool.sandbox_timeout == 30
    assert e2b_tool.tool_description == E2B_PYTHONCODE_INTERPRETER_TOOL_DESCRIPTION
    assert e2b_tool.tool_description.name == "python_code_interpreter"


def test_tool_description_structure():
    """Test that the tool description has the correct structure."""
    desc = E2B_PYTHONCODE_INTERPRETER_TOOL_DESCRIPTION
    assert desc.name == "python_code_interpreter"
    assert "Execute Python code in a secure sandbox environment" in desc.description
    assert "python_code" in desc.tool_properties
    assert desc.tool_properties["python_code"]["type"] == "string"
    assert "python_code" in desc.required_tool_properties


def test_execute_simple_python_code(e2b_tool, e2b_api_key):
    """Test executing simple Python code that returns a value."""
    python_code = "print('Hello, World!'); x = 42; x"

    result = e2b_tool.execute_python_code(python_code)

    # Parse the JSON result
    result_data = json.loads(result)

    # Check that the execution was successful
    assert "error" in result_data
    assert "logs" in result_data
    assert "results" in result_data

    # Check that there's no error
    assert result_data["error"] is None

    # Parse the logs JSON string
    logs = json.loads(result_data["logs"])
    assert "stdout" in logs
    assert "stderr" in logs

    # Check stdout contains our print statement
    assert "Hello, World!" in logs["stdout"][0]

    # Check the result is 42
    assert len(result_data["results"]) > 0
    assert result_data["results"][0]["text"] == "42"


def test_execute_python_code_with_imports(e2b_tool, e2b_api_key):
    """Test executing Python code that uses standard library imports."""
    python_code = """
import math
import datetime

radius = 5
area = math.pi * radius ** 2
current_time = datetime.datetime.now().strftime("%Y-%m-%d")

print(f"Circle area: {area:.2f}")
print(f"Current date: {current_time}")

result = {"area": area, "date": current_time}
result
"""

    result = e2b_tool.execute_python_code(python_code)
    result_data = json.loads(result)

    assert "error" in result_data
    assert "logs" in result_data
    assert "results" in result_data
    assert result_data["error"] is None

    # Parse the logs JSON string
    logs = json.loads(result_data["logs"])
    assert "stdout" in logs
    assert "stderr" in logs

    # Check stdout contains our print statements
    assert "Circle area:" in logs["stdout"][0]
    assert "Current date:" in logs["stdout"][0]

    # Check the result is a dictionary
    assert len(result_data["results"]) > 0
    result_obj = result_data["results"][0]
    assert "json" in result_obj
    assert "area" in result_obj["json"]
    assert "date" in result_obj["json"]


def test_execute_python_code_with_error(e2b_tool, e2b_api_key):
    """Test executing Python code that raises an error."""
    python_code = """
x = 10
y = 0
result = x / y  # This will raise a ZeroDivisionError
"""

    result = e2b_tool.execute_python_code(python_code)
    result_data = json.loads(result)

    assert "error" in result_data
    assert "logs" in result_data
    assert "results" in result_data

    # Check that there is an error
    assert result_data["error"] is not None

    # Parse the error JSON
    error_data = json.loads(result_data["error"])
    assert "name" in error_data
    assert "value" in error_data
    assert error_data["name"] == "ZeroDivisionError"
    assert "division by zero" in error_data["value"]


def test_execute_python_code_with_file_operations(e2b_tool, e2b_api_key):
    """Test executing Python code that performs file operations."""
    python_code = """
# Create a file and write to it
with open('test_file.txt', 'w') as f:
    f.write('Hello from E2B sandbox!')

# Read the file back
with open('test_file.txt', 'r') as f:
    content = f.read()

print(f"File content: {content}")

# List files in current directory
import os
files = os.listdir('.')

{"content": content, "files": files}
"""

    result = e2b_tool.execute_python_code(python_code)
    result_data = json.loads(result)

    assert "error" in result_data
    assert "logs" in result_data
    assert "results" in result_data
    assert result_data["error"] is None

    # Parse the logs JSON string
    logs = json.loads(result_data["logs"])
    assert "stdout" in logs
    assert "stderr" in logs

    # Check stdout contains our print statement
    assert "File content: Hello from E2B sandbox!" in logs["stdout"][0]

    # Check the result contains the expected data
    assert len(result_data["results"]) > 0
    result_obj = result_data["results"][0]
    assert "json" in result_obj
    assert result_obj["json"]["content"] == "Hello from E2B sandbox!"
    assert "test_file.txt" in result_obj["json"]["files"]


def test_execute_python_code_with_data_processing(e2b_tool, e2b_api_key):
    """Test executing Python code that processes data."""
    python_code = """
# Create some sample data
data = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]

# Calculate statistics
total = sum(data)
average = total / len(data)
squared = [x**2 for x in data]
even_numbers = [x for x in data if x % 2 == 0]

print(f"Total: {total}")
print(f"Average: {average}")
print(f"Even numbers: {even_numbers}")

{
    "total": total,
    "average": average,
    "squared": squared,
    "even_numbers": even_numbers,
    "count": len(data)
}
"""

    result = e2b_tool.execute_python_code(python_code)
    result_data = json.loads(result)

    assert "error" in result_data
    assert "logs" in result_data
    assert "results" in result_data
    assert result_data["error"] is None

    # Parse the logs JSON string
    logs = json.loads(result_data["logs"])
    assert "stdout" in logs
    assert "stderr" in logs

    # Check stdout contains our print statements
    assert "Total: 55" in logs["stdout"][0]
    assert "Average: 5.5" in logs["stdout"][0]
    assert "Even numbers: [2, 4, 6, 8, 10]" in logs["stdout"][0]

    # Check the result contains the expected data
    assert len(result_data["results"]) > 0
    result_obj = result_data["results"][0]
    assert "json" in result_obj
    result_data_obj = result_obj["json"]
    assert result_data_obj["total"] == 55
    assert result_data_obj["average"] == 5.5
    assert result_data_obj["count"] == 10
    assert result_data_obj["even_numbers"] == [2, 4, 6, 8, 10]


@pytest.mark.anyio
async def test_run_without_trace_simple_code(e2b_tool, e2b_api_key):
    """Test the async _run_without_trace method with simple code."""
    python_code = "print('Async test'); 2 + 2"

    result = await e2b_tool._run_without_trace(python_code=python_code)

    assert isinstance(result, AgentPayload)
    assert len(result.messages) == 1
    assert isinstance(result.messages[0], ChatMessage)
    assert result.messages[0].role == "assistant"

    # Parse the content
    content = result.messages[0].content

    # The content is a JSON string that contains another JSON string
    # First parse the outer JSON
    execution_data = json.loads(content)

    # If execution_data is still a string, parse it again
    if isinstance(execution_data, str):
        execution_data = json.loads(execution_data)

    assert "error" in execution_data
    assert "logs" in execution_data
    assert "results" in execution_data
    assert execution_data["error"] is None

    # Parse the logs JSON string
    logs = json.loads(execution_data["logs"])
    assert "Async test" in logs["stdout"][0]

    # Check the result
    assert len(execution_data["results"]) > 0
    assert execution_data["results"][0]["text"] == "4"

    # Check artifacts
    assert "execution_result" in result.artifacts
    # Parse the JSON string in artifacts before comparison
    artifacts_execution_data = json.loads(result.artifacts["execution_result"])
    assert artifacts_execution_data == execution_data


@pytest.mark.anyio
async def test_run_without_trace_complex_code(e2b_tool, e2b_api_key):
    """Test the async _run_without_trace method with complex code."""
    python_code = """
import json
import random

# Generate some random data
data = {
    "numbers": [random.randint(1, 100) for _ in range(5)],
    "message": "Hello from async test",
    "timestamp": "2024-01-01"
}

# Process the data
total = sum(data["numbers"])
average = total / len(data["numbers"])

result = {
    "original_data": data,
    "statistics": {
        "total": total,
        "average": average,
        "count": len(data["numbers"])
    }
}

print(f"Processed {len(data['numbers'])} numbers")
json.dumps(result)
"""

    result = await e2b_tool._run_without_trace(python_code=python_code)

    assert isinstance(result, AgentPayload)
    assert len(result.messages) == 1
    assert result.messages[0].role == "assistant"

    # Parse the content
    content = result.messages[0].content

    # The content is a JSON string that contains another JSON string
    # First parse the outer JSON
    execution_data = json.loads(content)

    # If execution_data is still a string, parse it again
    if isinstance(execution_data, str):
        execution_data = json.loads(execution_data)

    assert "error" in execution_data
    assert "logs" in execution_data
    assert "results" in execution_data
    assert execution_data["error"] is None

    # Parse the logs JSON string
    logs = json.loads(execution_data["logs"])
    assert "Processed 5 numbers" in logs["stdout"][0]

    # Check the result
    assert len(execution_data["results"]) > 0
    result_obj = execution_data["results"][0]
    assert "text" in result_obj

    # The result should be a JSON string
    result_json = result_obj["text"]
    result_data = json.loads(result_json)

    assert "original_data" in result_data
    assert "statistics" in result_data
    assert result_data["statistics"]["count"] == 5


def test_missing_api_key():
    """Test that the tool raises an error when E2B API key is not configured."""
    # Mock settings to return None for E2B_API_KEY
    with pytest.MonkeyPatch().context() as m:
        m.setattr("settings.settings.E2B_API_KEY", None)

        # Create a tool with explicit None API key
        tool = PythonCodeInterpreterE2BTool(
            trace_manager=MagicMock(spec=TraceManager),
            component_instance_name="test_no_api_key",
            e2b_api_key=None,
        )

        # Should raise ValueError when no API key is available
        with pytest.raises(ValueError, match="E2B API key not configured"):
            tool.execute_python_code("print('test')")


def test_sandbox_timeout_configuration():
    """Test that the tool respects the sandbox timeout configuration."""
    tool = PythonCodeInterpreterE2BTool(
        trace_manager=MagicMock(spec=TraceManager),
        component_instance_name="test_timeout",
        sandbox_timeout=10,
    )

    assert tool.sandbox_timeout == 10
