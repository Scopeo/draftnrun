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


def test_docx_generation_with_mock(docx_tool, tmp_path):
    """Test that DOCX is generated with mocked conversion."""
    # Use pytest's tmp_path as a writable temp directory for CI safety
    mock_params = Mock()
    mock_params.uuid_for_temp_folder = str(tmp_path / "test-uuid-12345")

    # Mock the markdown_to_word function to avoid actual file creation
    with (
        patch("engine.temps_folder_utils.get_tracing_span", return_value=mock_params),
        patch("engine.agent.docx_generation_tool.markdown_to_word") as mock_conversion,
    ):
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

        # Verify that markdown_to_word was called
        mock_conversion.assert_called_once()
        args, kwargs = mock_conversion.call_args
        assert len(args) == 2
        # First arg should be temp markdown file path
        assert args[0].endswith(".md")
        # Second arg should be output DOCX path
        assert args[1].endswith(".docx")

        # Clean up the directory if it exists
        output_dir = get_output_dir()
        if output_dir.exists():
            import shutil

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

        # Clean up the directory
        import shutil

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
    """Test that temporary markdown files are properly cleaned up."""
    # Use pytest's tmp_path as a writable temp directory for CI safety
    mock_params = Mock()
    mock_params.uuid_for_temp_folder = str(tmp_path / "test-uuid-12345")

    with (
        patch("engine.temps_folder_utils.get_tracing_span", return_value=mock_params),
        patch("engine.agent.docx_generation_tool.Path.unlink") as mock_unlink,
    ):
        # Call async function from sync test
        result = asyncio.run(docx_tool._run_without_io_trace(markdown_content=MARKDOWN_CONTENT))

        # Verify that temporary file cleanup was called
        mock_unlink.assert_called_once()

        # Verify successful result
        assert result.is_final is True
        assert result.error is None
        assert "DOCX generated successfully" in result.messages[0].content
