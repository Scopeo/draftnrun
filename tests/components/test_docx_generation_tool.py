import asyncio
import shutil
from unittest.mock import MagicMock, Mock, patch

import pytest

from engine.components.component import ComponentAttributes
from engine.components.docx_generation_tool import DOCXGenerationTool, DOCXGenerationToolInputs
from engine.temps_folder_utils import get_output_dir
from engine.trace.trace_manager import TraceManager

MARKDOWN_CONTENT = """# Test Document
This is a test document with **bold** and *italic* text.

## Features
- Bullet point 1
- Bullet point 2

> This is a blockquote.

### Code Example
```python
def hello_world():
    print("Hello, World!")
```
"""


@pytest.fixture
def mock_trace_manager():
    return MagicMock(spec=TraceManager)


@pytest.fixture
def docx_tool(mock_trace_manager):
    """Create a DOCX generation tool instance."""
    return DOCXGenerationTool(
        trace_manager=mock_trace_manager,
        component_attributes=ComponentAttributes(component_instance_name="test_docx_tool"),
    )


def test_docx_generation_real_file(docx_tool, tmp_path):
    """Test real DOCX file generation without mocks."""
    # Use pytest's tmp_path as a writable temp directory for CI safety
    mock_params = Mock()
    mock_params.uuid_for_temp_folder = str(tmp_path / "test-uuid-12345")

    with patch("engine.temps_folder_utils.get_tracing_span", return_value=mock_params):
        # Call async function from sync test
        inputs = DOCXGenerationToolInputs(markdown_content=MARKDOWN_CONTENT, output_filename=None)
        result = asyncio.run(docx_tool._run_without_io_trace(inputs=inputs, ctx={}))

        # Verify result structure
        assert hasattr(result, "output_message")
        assert hasattr(result, "artifacts")
        assert "file has been generated successfully" in result.output_message

        # Get the DOCX filename from artifacts
        docx_filename = result.artifacts.get("docx_filename")
        assert docx_filename is not None
        assert docx_filename.endswith(".docx")

        # Verify the actual file was created
        docx_path = get_output_dir() / docx_filename
        assert docx_path.exists()
        assert docx_path.is_file()
        assert docx_path.suffix == ".docx"

        # Verify file size is reasonable (not empty)
        assert docx_path.stat().st_size > 100  # Should be at least 100 bytes

        # Clean up the directory if it exists
        output_dir = get_output_dir()
        if output_dir.exists():
            shutil.rmtree(output_dir)


def test_docx_generation_with_actual_conversion(docx_tool, tmp_path):
    """Test that DOCX is generated with actual file creation."""
    # Use pytest's tmp_path as a writable temp directory for CI safety
    mock_params = Mock()
    mock_params.uuid_for_temp_folder = str(tmp_path / "test-uuid-12345")

    with patch("engine.temps_folder_utils.get_tracing_span", return_value=mock_params):
        # Call async function from sync test
        inputs = DOCXGenerationToolInputs(markdown_content=MARKDOWN_CONTENT, output_filename=None)
        result = asyncio.run(docx_tool._run_without_io_trace(inputs=inputs, ctx={}))

        # Verify result structure
        assert hasattr(result, "output_message")
        assert hasattr(result, "artifacts")
        assert "file has been generated successfully" in result.output_message

        # Get the DOCX filename from artifacts
        docx_filename = result.artifacts.get("docx_filename")
        assert docx_filename is not None
        docx_path = get_output_dir() / docx_filename

        # Verify DOCX file exists
        assert docx_path.exists()
        assert docx_path.is_file()
        assert docx_path.suffix == ".docx"

        # Verify file size is reasonable (not empty)
        assert docx_path.stat().st_size > 100  # Should be at least 100 bytes

        # Clean up the DOCX file
        docx_path.unlink()
        assert not docx_path.exists()

        shutil.rmtree(docx_path.parent)
        assert not docx_path.parent.exists()


def test_docx_generation_empty_content(docx_tool):
    """Test error handling when no markdown content is provided."""
    # Call async function from sync test with empty content
    inputs = DOCXGenerationToolInputs(markdown_content="", output_filename=None)
    result = asyncio.run(docx_tool._run_without_io_trace(inputs=inputs, ctx={}))

    # Verify error handling
    assert hasattr(result, "output_message")
    assert "No markdown content provided" in result.output_message


def test_docx_generation_no_content_kwarg(docx_tool):
    """Test error handling when markdown_content is empty (Pydantic validation)."""
    # With Pydantic, we test empty string handling (missing field would fail at validation)
    inputs = DOCXGenerationToolInputs(markdown_content="", output_filename=None)
    result = asyncio.run(docx_tool._run_without_io_trace(inputs=inputs, ctx={}))

    # Verify error handling
    assert hasattr(result, "output_message")
    assert "No markdown content provided" in result.output_message


def test_docx_generation_temp_file_cleanup(docx_tool, tmp_path):
    """Test that DOCX generation works and cleans up properly."""

    mock_params = Mock()
    mock_params.uuid_for_temp_folder = str(tmp_path / "test-uuid-12345")

    with patch("engine.temps_folder_utils.get_tracing_span", return_value=mock_params):
        # Call async function from sync test
        inputs = DOCXGenerationToolInputs(markdown_content=MARKDOWN_CONTENT, output_filename=None)
        result = asyncio.run(docx_tool._run_without_io_trace(inputs=inputs, ctx={}))

        # Verify successful result
        assert hasattr(result, "output_message")
        assert hasattr(result, "artifacts")
        assert "file has been generated successfully" in result.output_message

        # Verify the file was created
        docx_filename = result.artifacts.get("docx_filename")
        assert docx_filename is not None

        docx_path = get_output_dir() / docx_filename
        assert docx_path.exists()

        # Clean up
        output_dir = get_output_dir()
        if output_dir.exists():
            shutil.rmtree(output_dir)
