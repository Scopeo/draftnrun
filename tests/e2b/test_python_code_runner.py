import asyncio
import base64
import json
import uuid
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
import pytest_asyncio

from engine.components.tools.python_code_runner import (
    PythonCodeRunner,
    PythonCodeRunnerToolInputs,
    PythonCodeRunnerToolOutputs,
)
from engine.components.types import ComponentAttributes
from engine.trace.span_context import TracingSpanParams, set_tracing_span
from engine.trace.trace_manager import TraceManager


@pytest.fixture
def mock_trace_manager():
    return MagicMock(spec=TraceManager)


@pytest_asyncio.fixture
async def e2b_tool(mock_trace_manager):
    """Create a Python code runner tool instance."""
    tool = PythonCodeRunner(
        trace_manager=mock_trace_manager,
        component_attributes=ComponentAttributes(
            component_instance_name="test_e2b_tool",
        ),
        timeout=30,
    )
    yield tool
    await asyncio.sleep(0.1)


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


def test_execute_simple_python_code(e2b_tool):
    """Test executing simple Python code that returns a value."""
    python_code = "print('Hello, World!'); x = 42; x"

    result_data, _ = asyncio.run(e2b_tool.execute_python_code(python_code))

    assert result_data["error"] is None
    assert "Hello, World!" in result_data["stdout"][0]
    assert len(result_data["results"]) > 0
    assert result_data["results"][0].text == "42"


def test_execute_python_code_with_imports(e2b_tool):
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

    assert result_data["error"] is None
    assert "Circle area:" in result_data["stdout"][0]
    assert "Current date:" in result_data["stdout"][0]
    assert len(result_data["results"]) > 0
    result_obj = result_data["results"][0]
    assert hasattr(result_obj, "json") and result_obj.json is not None
    assert "area" in result_obj.json
    assert "date" in result_obj.json


def test_execute_python_code_with_error(e2b_tool):
    """Test executing Python code that raises an error."""
    python_code = """
x = 10
y = 0
result = x / y  # This will raise a ZeroDivisionError
"""

    result_data, _ = asyncio.run(e2b_tool.execute_python_code(python_code))

    assert result_data["error"] is not None
    assert isinstance(result_data["error"], str)
    assert "ZeroDivisionError" in result_data["error"] or "division by zero" in result_data["error"]


def test_execute_python_code_with_file_operations(e2b_tool):
    """Test executing Python code that performs file operations."""
    python_code = """
with open('test_file.txt', 'w') as f:
    f.write('Hello from E2B sandbox!')

with open('test_file.txt', 'r') as f:
    content = f.read()

print(f"File content: {content}")

import os
files = os.listdir('.')

{"content": content, "files": files}
"""

    result_data, _ = asyncio.run(e2b_tool.execute_python_code(python_code))

    assert result_data["error"] is None
    assert "File content: Hello from E2B sandbox!" in result_data["stdout"][0]
    assert len(result_data["results"]) > 0
    result_obj = result_data["results"][0]
    assert hasattr(result_obj, "json") and result_obj.json is not None
    assert result_obj.json["content"] == "Hello from E2B sandbox!"
    assert "test_file.txt" in result_obj.json["files"]


def test_execute_python_code_with_data_processing(e2b_tool):
    """Test executing Python code that processes data."""
    python_code = """
data = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]

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

    assert result_data["error"] is None
    assert "Total: 55" in result_data["stdout"][0]
    assert "Average: 5.5" in result_data["stdout"][0]
    assert "Even numbers: [2, 4, 6, 8, 10]" in result_data["stdout"][0]
    assert len(result_data["results"]) > 0
    result_obj = result_data["results"][0]
    assert hasattr(result_obj, "json") and result_obj.json is not None
    assert result_obj.json["total"] == 55
    assert result_obj.json["average"] == 5.5
    assert result_obj.json["count"] == 10
    assert result_obj.json["even_numbers"] == [2, 4, 6, 8, 10]


def test_execute_python_code_with_single_image(e2b_tool):
    """Test executing Python code that generates a single matplotlib plot."""
    python_code = """
import matplotlib.pyplot as plt
import numpy as np

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

    assert result_data["error"] is None

    images = e2b_tool._save_images_from_results(result_data, records)
    assert len(images) == 1
    image_data = images[0]
    assert isinstance(image_data, str)
    assert len(image_data) > 0
    decoded = base64.b64decode(image_data)
    assert len(decoded) > 0


def test_execute_python_code_with_multiple_images(e2b_tool):
    """Test executing Python code that generates multiple matplotlib plots."""
    python_code = """
import matplotlib.pyplot as plt
import numpy as np

x = np.linspace(0, 2*np.pi, 10)

plt.figure(figsize=(6, 4))
plt.plot(x, np.sin(x), 'b-', label='sine')
plt.title('Sine Wave')
plt.legend()
plt.show()

plt.figure(figsize=(6, 4))
plt.plot(x, np.cos(x), 'r-', label='cosine')
plt.title('Cosine Wave')
plt.legend()
plt.show()

plt.figure(figsize=(8, 5))
plt.plot(x, np.sin(x), 'b-', label='sine')
plt.plot(x, np.cos(x), 'r-', label='cosine')
plt.title('Sine and Cosine Waves')
plt.legend()
plt.show()

print("Three plots generated!")
"""

    result_data, records = asyncio.run(e2b_tool.execute_python_code(python_code))

    assert result_data["error"] is None

    images = e2b_tool._save_images_from_results(result_data, records)
    assert len(images) == 3
    for i, image_data in enumerate(images):
        assert isinstance(image_data, str)
        assert len(image_data) > 0
        decoded = base64.b64decode(image_data)
        assert len(decoded) > 0


def test_execute_python_code_with_no_images(e2b_tool):
    """Test executing Python code that doesn't generate any images."""
    python_code = """
import numpy as np

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

    assert result_data["error"] is None
    images = e2b_tool._save_images_from_results(result_data, records)
    assert len(images) == 0


def test_run_without_io_trace_with_single_image(e2b_tool):
    """Test _run_without_io_trace with image generation."""
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
    assert "execution_result" in result.artifacts
    assert "images" in result.artifacts
    images = result.artifacts["images"]
    assert isinstance(images, list)
    assert len(images) == 1
    assert isinstance(images[0], str) and len(images[0]) > 0
    assert "[1 image(s) generated and included in artifacts" in result.output


def test_run_without_io_trace_with_multiple_images(e2b_tool):
    """Test _run_without_io_trace with multiple image generation."""
    python_code = """
import matplotlib.pyplot as plt
import numpy as np

x = np.linspace(0, 4*np.pi, 50)

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
    assert "images" in result.artifacts
    images = result.artifacts["images"]
    assert len(images) == 2
    for image_data in images:
        assert isinstance(image_data, str) and len(image_data) > 0
    assert "[2 image(s) generated and included in artifacts" in result.output


def test_run_without_io_trace_no_images(e2b_tool):
    """Test _run_without_io_trace with no image generation."""
    python_code = "print('No images here!'); result = {'value': 42}; result"

    inputs = PythonCodeRunnerToolInputs(python_code=python_code)
    result = asyncio.run(e2b_tool._run_without_io_trace(inputs, {}))

    assert isinstance(result, PythonCodeRunnerToolOutputs)
    assert "execution_result" in result.artifacts
    assert "images" not in result.artifacts
    assert "image(s) generated" not in result.output


def test_run_without_io_trace_simple_code(e2b_tool):
    """Test _run_without_io_trace with simple code."""
    python_code = "print('Async test'); 2 + 2"

    inputs = PythonCodeRunnerToolInputs(python_code=python_code)
    result = asyncio.run(e2b_tool._run_without_io_trace(inputs, {}))

    assert isinstance(result, PythonCodeRunnerToolOutputs)
    execution_data = json.loads(result.output)
    assert execution_data["error"] is None
    assert "Async test" in execution_data["stdout"][0]
    assert len(execution_data["results"]) > 0
    assert "4" in execution_data["results"][0]
    assert "execution_result" in result.artifacts


def test_run_without_io_trace_complex_code(e2b_tool):
    """Test _run_without_io_trace with complex code."""
    python_code = """
import json
import random

data = {
    "numbers": [random.randint(1, 100) for _ in range(5)],
    "message": "Hello from async test",
    "timestamp": "2024-01-01"
}

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
    execution_data = json.loads(result.output)
    assert execution_data["error"] is None
    assert "Processed 5 numbers" in execution_data["stdout"][0]
    assert len(execution_data["results"]) > 0
    result_obj = execution_data["results"][0]
    assert "original_data" in result_obj
    assert "statistics" in result_obj
    assert '"count": 5' in result_obj


def test_execute_python_code_with_shared_sandbox_from_context():
    """Test that the tool uses shared sandbox from tracing context."""
    tool = PythonCodeRunner(
        trace_manager=MagicMock(spec=TraceManager),
        component_attributes=ComponentAttributes(
            component_instance_name="test_shared_sandbox",
        ),
    )

    mock_shared_sandbox = AsyncMock()
    mock_execution = Mock()
    mock_execution.error = None
    mock_execution.results = []
    mock_execution.logs = Mock(stdout=["Test output"], stderr=[])
    mock_shared_sandbox.run_code.return_value = mock_execution
    mock_shared_sandbox.is_running.return_value = True

    mock_params = TracingSpanParams(
        project_id="test_project",
        organization_id="test_org",
        organization_llm_providers=["test_provider"],
        uuid_for_temp_folder="/tmp/test",
        shared_sandbox=mock_shared_sandbox,
    )

    with patch("engine.components.tools.sandbox_utils.get_tracing_span", return_value=mock_params):
        with patch("engine.components.tools.sandbox_utils.AsyncSandbox") as mock_sandbox_class:
            result_data, _ = asyncio.run(tool.execute_python_code("print('test')"))

            mock_sandbox_class.create.assert_not_called()
            mock_shared_sandbox.run_code.assert_called_once()
            assert "error" in result_data
            assert "stdout" in result_data
