import pytest
import json
import os
import base64
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
        timeout=30,
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

    result_data = e2b_tool.execute_python_code(python_code)

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

    result_data = e2b_tool.execute_python_code(python_code)

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

    result_data = e2b_tool.execute_python_code(python_code)

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

    result_data = e2b_tool.execute_python_code(python_code)

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

    result_data = e2b_tool.execute_python_code(python_code)

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


def test_execute_python_code_with_single_image(e2b_tool, e2b_api_key):
    """Test executing Python code that generates a single matplotlib plot."""
    python_code = """
import matplotlib.pyplot as plt
import numpy as np

# Create a simple plot
x = np.linspace(0, 2*np.pi, 10)
y = np.sin(x)

plt.figure(figsize=(6, 4))
plt.plot(x, y, 'b-', label='sine wave')
plt.title('Single Sine Wave Plot')
plt.xlabel('X')
plt.ylabel('sin(X)')
plt.legend()
plt.show()

print("Single plot generated!")
"""

    result_data = e2b_tool.execute_python_code(python_code)

    # Check that execution was successful
    assert result_data["error"] is None

    # Test image extraction
    images = e2b_tool._extract_images_from_results(result_data)

    # Should have exactly one image
    assert len(images) == 1

    # Check that the image is a valid base64 string
    image_data = images[0]
    assert isinstance(image_data, str)
    assert len(image_data) > 0

    # Verify it's valid base64
    try:
        decoded = base64.b64decode(image_data)
        assert len(decoded) > 0
    except Exception:
        pytest.fail("Image data is not valid base64")


def test_execute_python_code_with_multiple_images(e2b_tool, e2b_api_key):
    """Test executing Python code that generates multiple matplotlib plots."""
    python_code = """
import matplotlib.pyplot as plt
import numpy as np

x = np.linspace(0, 2*np.pi, 10)

# First plot - sine wave
plt.figure(figsize=(6, 4))
plt.plot(x, np.sin(x), 'b-', label='sine')
plt.title('Sine Wave')
plt.legend()
plt.show()

# Second plot - cosine wave
plt.figure(figsize=(6, 4))
plt.plot(x, np.cos(x), 'r-', label='cosine')
plt.title('Cosine Wave')
plt.legend()
plt.show()

# Third plot - both waves
plt.figure(figsize=(8, 5))
plt.plot(x, np.sin(x), 'b-', label='sine')
plt.plot(x, np.cos(x), 'r-', label='cosine')
plt.title('Sine and Cosine Waves')
plt.legend()
plt.show()

print("Three plots generated!")
"""

    result_data = e2b_tool.execute_python_code(python_code)

    # Check that execution was successful
    assert result_data["error"] is None

    # Test image extraction
    images = e2b_tool._extract_images_from_results(result_data)

    # Should have exactly three images
    assert len(images) == 3

    # Check that all images are valid base64 strings
    for i, image_data in enumerate(images):
        assert isinstance(image_data, str)
        assert len(image_data) > 0

        # Verify it's valid base64
        try:
            decoded = base64.b64decode(image_data)
            assert len(decoded) > 0
        except Exception:
            pytest.fail(f"Image {i+1} data is not valid base64")


def test_execute_python_code_with_no_images(e2b_tool, e2b_api_key):
    """Test executing Python code that doesn't generate any images."""
    python_code = """
import numpy as np

# Just do some calculations, no plots
x = np.linspace(0, 2*np.pi, 10)
y = np.sin(x)
result = {
    "max_value": float(np.max(y)),
    "min_value": float(np.min(y)),
    "mean_value": float(np.mean(y))
}

print("Calculations completed!")
result
"""

    result_data = e2b_tool.execute_python_code(python_code)

    # Check that execution was successful
    assert result_data["error"] is None

    # Test image extraction
    images = e2b_tool._extract_images_from_results(result_data)

    # Should have no images
    assert len(images) == 0


@pytest.mark.anyio
async def test_run_without_trace_with_single_image(e2b_tool, e2b_api_key):
    """Test the async _run_without_trace method with image generation."""
    python_code = """
import matplotlib.pyplot as plt
import numpy as np

x = np.linspace(0, 2*np.pi, 20)
y = np.sin(x)

plt.figure(figsize=(8, 6))
plt.plot(x, y, 'g-', linewidth=2)
plt.title('Async Test Plot')
plt.grid(True)
plt.show()

print("Async image test completed!")
"""

    result = await e2b_tool._run_without_trace(python_code=python_code)

    assert isinstance(result, AgentPayload)
    assert len(result.messages) == 1
    assert isinstance(result.messages[0], ChatMessage)
    assert result.messages[0].role == "assistant"

    # Check that execution_result is in artifacts
    assert "execution_result" in result.artifacts

    # Check that images are in artifacts
    assert "images" in result.artifacts
    images = result.artifacts["images"]
    assert isinstance(images, list)
    assert len(images) == 1

    # Verify the image is valid base64
    image_data = images[0]
    assert isinstance(image_data, str)
    assert len(image_data) > 0

    try:
        decoded = base64.b64decode(image_data)
        assert len(decoded) > 0
    except Exception:
        pytest.fail("Image data in artifacts is not valid base64")

    # Check that the response message mentions the image
    content = result.messages[0].content
    assert "[1 image(s) generated and included in artifacts]" in content


@pytest.mark.anyio
async def test_run_without_trace_with_multiple_images(e2b_tool, e2b_api_key):
    """Test the async _run_without_trace method with multiple image generation."""
    python_code = """
import matplotlib.pyplot as plt
import numpy as np

x = np.linspace(0, 4*np.pi, 50)

# Generate two different plots
for i, func in enumerate([np.sin, np.cos]):
    plt.figure(figsize=(6, 4))
    plt.plot(x, func(x))
    plt.title(f'Plot {i+1}: {func.__name__}(x)')
    plt.show()

print("Two async plots generated!")
"""

    result = await e2b_tool._run_without_trace(python_code=python_code)

    assert isinstance(result, AgentPayload)
    assert len(result.messages) == 1

    # Check that images are in artifacts
    assert "images" in result.artifacts
    images = result.artifacts["images"]
    assert isinstance(images, list)
    assert len(images) == 2

    # Verify both images are valid base64
    for i, image_data in enumerate(images):
        assert isinstance(image_data, str)
        assert len(image_data) > 0

        try:
            decoded = base64.b64decode(image_data)
            assert len(decoded) > 0
        except Exception:
            pytest.fail(f"Image {i+1} data in artifacts is not valid base64")

    # Check that the response message mentions the correct number of images
    content = result.messages[0].content
    assert "[2 image(s) generated and included in artifacts]" in content


@pytest.mark.anyio
async def test_run_without_trace_no_images(e2b_tool, e2b_api_key):
    """Test the async _run_without_trace method with no image generation."""
    python_code = "print('No images here!'); result = {'value': 42}; result"

    result = await e2b_tool._run_without_trace(python_code=python_code)

    assert isinstance(result, AgentPayload)
    assert len(result.messages) == 1

    # Check that execution_result is in artifacts
    assert "execution_result" in result.artifacts

    # Check that images are NOT in artifacts (since no images were generated)
    assert "images" not in result.artifacts

    # Check that the response message doesn't mention images
    content = result.messages[0].content
    assert "image(s) generated" not in content


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
    # The execution result is now stored as a dict in artifacts
    artifacts_execution_data = result.artifacts["execution_result"]
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

        tool = PythonCodeInterpreterE2BTool(
            trace_manager=MagicMock(spec=TraceManager),
            component_instance_name="test_no_api_key",
        )

        # Should raise ValueError when no API key is available
        with pytest.raises(ValueError, match="E2B API key not configured"):
            tool.execute_python_code("print('test')")


def test_sandbox_timeout_configuration():
    """Test that the tool respects the sandbox timeout configuration."""
    tool = PythonCodeInterpreterE2BTool(
        trace_manager=MagicMock(spec=TraceManager),
        component_instance_name="test_timeout",
        timeout=10,
    )

    assert tool.sandbox_timeout == 10
