import asyncio
from unittest.mock import MagicMock, Mock, patch

import pytest

from engine.agent.agent import ComponentAttributes
from engine.agent.pdf_generation_tool import DEFAULT_CSS_FORMATTING, PDFGenerationTool
from engine.temps_folder_utils import get_output_dir
from engine.trace.trace_manager import TraceManager

MARKDOWN_CONTENT = """# Test Document
This is a test document with **bold** and *italic* text.

## Features
- Bullet point 1
- Bullet point 2

> This is a blockquote.
"""


@pytest.fixture
def mock_trace_manager():
    return MagicMock(spec=TraceManager)


@pytest.fixture
def pdf_tool(mock_trace_manager):
    """Create a PDF generation tool instance."""
    return PDFGenerationTool(
        trace_manager=mock_trace_manager,
        component_attributes=ComponentAttributes(component_instance_name="test_pdf_tool"),
    )


def test_pdf_generation_and_cleanup(pdf_tool, tmp_path):
    """Test that PDF is generated and then cleaned up properly."""
    # Use pytest's tmp_path as a writable temp directory for CI safety
    mock_params = Mock()
    mock_params.uuid_for_temp_folder = str(tmp_path / "test-uuid-12345")

    # Mock weasyprint to avoid HTTP requests
    mock_html = Mock()
    mock_html.write_pdf = Mock()

    with (
        patch("engine.temps_folder_utils.get_tracing_span", return_value=mock_params),
        patch("engine.agent.pdf_generation_tool.HTML", return_value=mock_html),
        patch("engine.agent.pdf_generation_tool.CSS") as MockCSS,
    ):
        mock_css_instance = MockCSS.return_value
        # Call async function from sync test
        result = asyncio.run(pdf_tool._run_without_io_trace(markdown_content=MARKDOWN_CONTENT))

        # Verify result structure
        assert result.is_final is True
        assert result.error is None
        assert len(result.messages) == 1
        assert "PDF generated successfully" in result.messages[0].content

        # Get the PDF filename from artifacts
        artifacts = getattr(result, "artifacts", None) or result.__dict__.get("artifacts", {})
        pdf_filename = artifacts.get("pdf_filename")
        assert pdf_filename is not None
        pdf_path = get_output_dir() / pdf_filename

        MockCSS.assert_called_once_with(string=DEFAULT_CSS_FORMATTING)
        # Verify that weasyprint was called correctly
        mock_html.write_pdf.assert_called_once_with(str(pdf_path), stylesheets=[mock_css_instance])

        # Verify the directory was created
        assert pdf_path.parent.exists()
        assert pdf_path.parent.is_dir()

        # Clean up the directory
        import shutil

        shutil.rmtree(pdf_path.parent)
        assert not pdf_path.parent.exists()


def test_pdf_generation_with_actual_pdf(pdf_tool, tmp_path):
    """Test that PDF is generated with actual PDF creation (for integration testing)."""
    # Use pytest's tmp_path as a writable temp directory for CI safety
    mock_params = Mock()
    mock_params.uuid_for_temp_folder = str(tmp_path / "test-uuid-12345")

    with patch("engine.temps_folder_utils.get_tracing_span", return_value=mock_params):
        # Call async function from sync test
        result = asyncio.run(pdf_tool._run_without_io_trace(markdown_content=MARKDOWN_CONTENT))

        # Verify result structure
        assert result.is_final is True
        assert result.error is None
        assert len(result.messages) == 1
        assert "PDF generated successfully" in result.messages[0].content

        # Get the PDF filename from artifacts
        artifacts = getattr(result, "artifacts", None) or result.__dict__.get("artifacts", {})
        pdf_filename = artifacts.get("pdf_filename")
        assert pdf_filename is not None
        pdf_path = get_output_dir() / pdf_filename

        # Verify PDF file exists
        assert pdf_path.exists()
        assert pdf_path.is_file()
        assert pdf_path.suffix == ".pdf"

        # Verify file size is reasonable (not empty)
        assert pdf_path.stat().st_size > 100  # Should be at least 100 bytes

        # Clean up the PDF file
        pdf_path.unlink()
        assert not pdf_path.exists()

        # Clean up the directory
        import shutil

        shutil.rmtree(pdf_path.parent)
        assert not pdf_path.parent.exists()
