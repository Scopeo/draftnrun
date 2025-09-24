import shutil
import pytest
import asyncio
from unittest.mock import MagicMock, patch, Mock

from engine.agent.docx_generation_tool import DOCXGenerationTool
from engine.agent.agent import ComponentAttributes
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
        result = asyncio.run(docx_tool._run_without_io_trace(markdown_content=MARKDOWN_CONTENT))

        # Verify result structure
        assert result.is_final is True
        assert result.error is None
        assert len(result.messages) == 1
        assert "DOCX generated successfully" in result.messages[0].content

        # Get the DOCX filename from artifacts
        artifacts = getattr(result, "artifacts", None) or result.__dict__.get("artifacts", {})
        docx_filename = artifacts.get("docx_filename")
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
        result = asyncio.run(docx_tool._run_without_io_trace(markdown_content=MARKDOWN_CONTENT))

        # Verify result structure
        assert result.is_final is True
        assert result.error is None
        assert len(result.messages) == 1
        assert "DOCX generated successfully" in result.messages[0].content

        # Get the DOCX filename from artifacts
        artifacts = getattr(result, "artifacts", None) or result.__dict__.get("artifacts", {})
        docx_filename = artifacts.get("docx_filename")
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
    result = asyncio.run(docx_tool._run_without_io_trace(markdown_content=""))

    # Verify error handling
    assert result.is_final is True
    assert result.error is not None
    assert "No markdown content provided" in result.error
    assert len(result.messages) == 1
    assert "No markdown content provided" in result.messages[0].content


def test_docx_generation_no_content_kwarg(docx_tool):
    """Test error handling when markdown_content kwarg is missing."""
    # Call async function from sync test without markdown_content kwarg
    result = asyncio.run(docx_tool._run_without_io_trace())

    # Verify error handling
    assert result.is_final is True
    assert result.error is not None
    assert "No markdown content provided" in result.error
    assert len(result.messages) == 1
    assert "No markdown content provided" in result.messages[0].content


def test_docx_generation_temp_file_cleanup(docx_tool, tmp_path):
    """Test that DOCX generation works and cleans up properly."""

    mock_params = Mock()
    mock_params.uuid_for_temp_folder = str(tmp_path / "test-uuid-12345")

    with patch("engine.temps_folder_utils.get_tracing_span", return_value=mock_params):
        # Call async function from sync test
        result = asyncio.run(docx_tool._run_without_io_trace(markdown_content=MARKDOWN_CONTENT))

        # Verify successful result
        assert result.is_final is True
        assert result.error is None
        assert "DOCX generated successfully" in result.messages[0].content

        # Verify the file was created
        artifacts = getattr(result, "artifacts", None) or result.__dict__.get("artifacts", {})
        docx_filename = artifacts.get("docx_filename")
        assert docx_filename is not None

        docx_path = get_output_dir() / docx_filename
        assert docx_path.exists()

        # Clean up
        output_dir = get_output_dir()
        if output_dir.exists():

            shutil.rmtree(output_dir)
