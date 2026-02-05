import asyncio
import base64
import json
import os
import uuid
from unittest.mock import MagicMock

import pytest
import pytest_asyncio

from engine.components.tools.python_code_runner import (
    PYTHON_CODE_RUNNER_TOOL_DESCRIPTION,
    PythonCodeRunner,
    PythonCodeRunnerToolInputs,
    PythonCodeRunnerToolOutputs,
)
from engine.components.types import ComponentAttributes
from engine.trace.span_context import set_tracing_span
from engine.trace.trace_manager import TraceManager


@pytest.fixture
def mock_trace_manager():
    return MagicMock(spec=TraceManager)


@pytest_asyncio.fixture
async def e2b_tool(mock_trace_manager):
    """Create an Python code runner tool instance."""
    tool = PythonCodeRunner(
        trace_manager=mock_trace_manager,
        component_attributes=ComponentAttributes(
            component_instance_name="test_e2b_tool",
        ),
        timeout=30,
    )
    yield tool
    # Cleanup: ensure any lingering HTTP connections are closed
    # The E2B library should handle this, but we'll give it a moment to complete
    await asyncio.sleep(0.1)


@pytest.fixture
def e2b_api_key():
    """Get E2B API key from environment or skip test if not available."""
    api_key = os.getenv("E2B_API_KEY")
    if not api_key:
        pytest.skip("E2B_API_KEY environment variable not set")
    return api_key


@pytest.fixture(autouse=True)
def setup_tracing_context():
    """Setup a unique tracing context for each test."""
    unique_uuid = f"/tmp/{uuid.uuid4()}"
    set_tracing_span(
        project_id="test_project",
        organization_id="test_org",
        organization_llm_providers=["test_provider"],
        uuid_for_temp_folder=unique_uuid,
    )


def test_tool_initialization(e2b_tool):
    """Test that the tool initializes correctly."""
    assert e2b_tool.component_attributes.component_instance_name == "test_e2b_tool"
    assert e2b_tool.sandbox_timeout == 30
    assert e2b_tool.tool_description == PYTHON_CODE_RUNNER_TOOL_DESCRIPTION
    assert e2b_tool.tool_description.name == "python_code_runner"


def test_tool_description_structure():
    """Test that the tool description has the correct structure."""
    desc = PYTHON_CODE_RUNNER_TOOL_DESCRIPTION
    assert desc.name == "python_code_runner"
    assert "Execute Python code in a secure sandbox environment" in desc.description
    assert "python_code" in desc.tool_properties
    assert desc.tool_properties["python_code"]["type"] == "string"
    assert "python_code" in desc.required_tool_properties


def test_execute_simple_python_code(e2b_tool, e2b_api_key):
    """Test executing simple Python code that returns a value."""
    python_code = "print('Hello, World!'); x = 42; x"

    result_data, _ = asyncio.run(e2b_tool.execute_python_code(python_code))

    # Check that the execution was successful
    assert "error" in result_data
    assert "stdout" in result_data
    assert "stderr" in result_data
    assert "results" in result_data

    # Check that there's no error
    assert result_data["error"] is None

    # Check stdout contains our print statement
    assert "Hello, World!" in result_data["stdout"][0]

    # Check the result is 42
    assert len(result_data["results"]) > 0
    assert result_data["results"][0].text == "42"


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

    result_data, _ = asyncio.run(e2b_tool.execute_python_code(python_code))

    assert "error" in result_data
    assert "stdout" in result_data
    assert "stderr" in result_data
    assert "results" in result_data
    assert result_data["error"] is None

    # Check stdout contains our print statements
    assert "Circle area:" in result_data["stdout"][0]
    assert "Current date:" in result_data["stdout"][0]

    # Check the result is a dictionary
    assert len(result_data["results"]) > 0
    result_obj = result_data["results"][0]
    assert hasattr(result_obj, "json") and result_obj.json is not None
    assert "area" in result_obj.json
    assert "date" in result_obj.json


def test_execute_python_code_with_error(e2b_tool, e2b_api_key):
    """Test executing Python code that raises an error."""
    python_code = """
x = 10
y = 0
result = x / y  # This will raise a ZeroDivisionError
"""

    result_data, _ = asyncio.run(e2b_tool.execute_python_code(python_code))

    assert "error" in result_data
    assert "stdout" in result_data
    assert "stderr" in result_data
    assert "results" in result_data

    # Check that there is an error
    assert result_data["error"] is not None

    # The error is a string, not JSON
    assert isinstance(result_data["error"], str)
    assert "ZeroDivisionError" in result_data["error"] or "division by zero" in result_data["error"]


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

    result_data, _ = asyncio.run(e2b_tool.execute_python_code(python_code))

    assert "error" in result_data
    assert "stdout" in result_data
    assert "stderr" in result_data
    assert "results" in result_data
    assert result_data["error"] is None

    # Check stdout contains our print statement
    assert "File content: Hello from E2B sandbox!" in result_data["stdout"][0]

    # Check the result contains the expected data
    assert len(result_data["results"]) > 0
    result_obj = result_data["results"][0]
    assert hasattr(result_obj, "json") and result_obj.json is not None
    assert result_obj.json["content"] == "Hello from E2B sandbox!"
    assert "test_file.txt" in result_obj.json["files"]


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

    result_data, _ = asyncio.run(e2b_tool.execute_python_code(python_code))

    assert "error" in result_data
    assert "stdout" in result_data
    assert "stderr" in result_data
    assert "results" in result_data
    assert result_data["error"] is None

    # Check stdout contains our print statements
    assert "Total: 55" in result_data["stdout"][0]
    assert "Average: 5.5" in result_data["stdout"][0]
    assert "Even numbers: [2, 4, 6, 8, 10]" in result_data["stdout"][0]

    # Check the result contains the expected data
    assert len(result_data["results"]) > 0
    result_obj = result_data["results"][0]
    assert hasattr(result_obj, "json") and result_obj.json is not None
    result_data_obj = result_obj.json
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

    result_data, records = asyncio.run(e2b_tool.execute_python_code(python_code))

    # Check that execution was successful
    assert result_data["error"] is None

    # Test image extraction
    images = e2b_tool._save_images_from_results(result_data, records)

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

    result_data, records = asyncio.run(e2b_tool.execute_python_code(python_code))

    # Check that execution was successful
    assert result_data["error"] is None

    # Test image extraction
    images = e2b_tool._save_images_from_results(result_data, records)

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
            pytest.fail(f"Image {i + 1} data is not valid base64")


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

    result_data, records = asyncio.run(e2b_tool.execute_python_code(python_code))

    # Check that execution was successful
    assert result_data["error"] is None

    # Test image extraction
    images = e2b_tool._save_images_from_results(result_data, records)

    # Should have no images
    assert len(images) == 0


def test_run_without_io_trace_with_single_image(e2b_tool, e2b_api_key):
    """Test the async _run_without_io_trace method with image generation."""
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

    inputs = PythonCodeRunnerToolInputs(python_code=python_code)
    result = asyncio.run(e2b_tool._run_without_io_trace(inputs, {}))

    assert isinstance(result, PythonCodeRunnerToolOutputs)

    # Check that execution_result is in artifacts
    assert "execution_result" in result.artifacts

    # Check that images are in artifacts
    assert "images" in result.artifacts
    images = result.artifacts["images"]
    assert isinstance(images, list)
    assert len(images) == 1

    # Verify the image is a valid file path string
    image_data = images[0]
    assert isinstance(image_data, str)
    assert len(image_data) > 0

    # Check that the response output mentions the image
    assert "[1 image(s) generated and included in artifacts" in result.output


def test_run_without_io_trace_with_multiple_images(e2b_tool, e2b_api_key):
    """Test the async _run_without_io_trace method with multiple image generation."""
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

    inputs = PythonCodeRunnerToolInputs(python_code=python_code)
    result = asyncio.run(e2b_tool._run_without_io_trace(inputs, {}))

    assert isinstance(result, PythonCodeRunnerToolOutputs)

    # Check that images are in artifacts
    assert "images" in result.artifacts
    images = result.artifacts["images"]
    assert isinstance(images, list)
    assert len(images) == 2

    # Verify both images are valid file path strings
    for i, image_data in enumerate(images):
        assert isinstance(image_data, str)
        assert len(image_data) > 0

    # Check that the response output mentions the correct number of images
    assert "[2 image(s) generated and included in artifacts" in result.output


def test_run_without_io_trace_no_images(e2b_tool, e2b_api_key):
    """Test the async _run_without_io_trace method with no image generation."""
    python_code = "print('No images here!'); result = {'value': 42}; result"

    inputs = PythonCodeRunnerToolInputs(python_code=python_code)
    result = asyncio.run(e2b_tool._run_without_io_trace(inputs, {}))

    assert isinstance(result, PythonCodeRunnerToolOutputs)

    # Check that execution_result is in artifacts
    assert "execution_result" in result.artifacts

    # Check that images are NOT in artifacts (since no images were generated)
    assert "images" not in result.artifacts

    # Check that the response output doesn't mention images
    assert "image(s) generated" not in result.output


def test_run_without_io_trace_simple_code(e2b_tool, e2b_api_key):
    """Test the async _run_without_io_trace method with simple code."""
    python_code = "print('Async test'); 2 + 2"

    inputs = PythonCodeRunnerToolInputs(python_code=python_code)
    result = asyncio.run(e2b_tool._run_without_io_trace(inputs, {}))

    assert isinstance(result, PythonCodeRunnerToolOutputs)

    # Parse the output content
    # The output is a JSON string
    execution_data = json.loads(result.output)

    assert "error" in execution_data
    assert "stdout" in execution_data
    assert "stderr" in execution_data
    assert "results" in execution_data
    assert execution_data["error"] is None

    # Check stdout
    assert "Async test" in execution_data["stdout"][0]

    # Check the result
    assert len(execution_data["results"]) > 0
    assert "4" in execution_data["results"][0]

    # Check artifacts
    assert "execution_result" in result.artifacts
    # The execution result is stored as a dict in artifacts (with non-serialized objects)
    artifacts_execution_data = result.artifacts["execution_result"]
    assert artifacts_execution_data["error"] == execution_data["error"]
    assert artifacts_execution_data["stdout"] == execution_data["stdout"]
    assert artifacts_execution_data["stderr"] == execution_data["stderr"]
    # Note: artifacts has Result objects while execution_data has serialized strings


def test_run_without_io_trace_complex_code(e2b_tool, e2b_api_key):
    """Test the async _run_without_io_trace method with complex code."""
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

    inputs = PythonCodeRunnerToolInputs(python_code=python_code)
    result = asyncio.run(e2b_tool._run_without_io_trace(inputs, {}))

    assert isinstance(result, PythonCodeRunnerToolOutputs)

    # Parse the output content
    # The output is a JSON string
    execution_data = json.loads(result.output)

    assert "error" in execution_data
    assert "stdout" in execution_data
    assert "stderr" in execution_data
    assert "results" in execution_data
    assert execution_data["error"] is None

    # Check stdout
    assert "Processed 5 numbers" in execution_data["stdout"][0]

    # Check the result
    assert len(execution_data["results"]) > 0
    result_obj = execution_data["results"][0]
    assert "Result(" in result_obj

    # The result should contain the JSON data within the Result() string
    # Extract the JSON from within Result(...) format
    assert "original_data" in result_obj
    assert "statistics" in result_obj
    assert '"count": 5' in result_obj


def test_missing_api_key():
    """Test that the tool raises an error when E2B API key is not configured."""
    with pytest.MonkeyPatch().context() as m:
        m.setattr("settings.settings.E2B_API_KEY", None)

        tool = PythonCodeRunner(
            trace_manager=MagicMock(spec=TraceManager),
            component_attributes=ComponentAttributes(
                component_instance_name="test_no_api_key",
            ),
        )
        with pytest.raises(ValueError, match="E2B API key not configured"):
            asyncio.run(tool.execute_python_code("print('test')"))


def test_sandbox_timeout_configuration():
    """Test that the tool respects the sandbox timeout configuration."""
    tool = PythonCodeRunner(
        trace_manager=MagicMock(spec=TraceManager),
        component_attributes=ComponentAttributes(
            component_instance_name="test_timeout",
        ),
        timeout=10,
    )

    assert tool.sandbox_timeout == 10


def test_execute_python_code_with_shared_sandbox_from_context(e2b_api_key):
    """Test that the tool uses shared sandbox from tracing context."""
    import asyncio
    from unittest.mock import AsyncMock, Mock, patch

    from engine.trace.span_context import TracingSpanParams

    tool = PythonCodeRunner(
        trace_manager=MagicMock(spec=TraceManager),
        component_attributes=ComponentAttributes(
            component_instance_name="test_shared_sandbox",
        ),
    )

    # Create a mock shared sandbox
    mock_shared_sandbox = AsyncMock()
    mock_execution = Mock()
    mock_execution.error = None
    mock_execution.results = []
    mock_execution.logs = Mock(stdout=["Test output"], stderr=[])
    mock_shared_sandbox.run_code.return_value = mock_execution

    # Mock the tracing context with a shared sandbox
    mock_params = TracingSpanParams(
        project_id="test_project",
        organization_id="test_org",
        organization_llm_providers=["test_provider"],
        uuid_for_temp_folder="/tmp/test",
        shared_sandbox=mock_shared_sandbox,
    )

    with patch("engine.components.tools.python_code_runner.get_tracing_span", return_value=mock_params):
        with patch("engine.components.tools.python_code_runner.AsyncSandbox") as mock_sandbox_class:
            result_data, _ = asyncio.run(tool.execute_python_code("print('test')"))

            # Should use the shared sandbox, not create a new one
            mock_sandbox_class.create.assert_not_called()
            mock_shared_sandbox.run_code.assert_called_once()

            # Verify result structure
            assert "error" in result_data
            assert "stdout" in result_data
            assert "stderr" in result_data
            assert "results" in result_data
