import pytest
import pytest_asyncio
from unittest.mock import MagicMock, patch, Mock
from pathlib import Path

from engine.agent.pdf_generation_tool import PDFGenerationTool
from engine.agent.agent import ComponentAttributes
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


@pytest_asyncio.fixture
async def pdf_tool(mock_trace_manager):
    """Create a PDF generation tool instance."""
    tool = PDFGenerationTool(
        trace_manager=mock_trace_manager,
        component_attributes=ComponentAttributes(component_instance_name="test_pdf_tool"),
    )
    yield tool


@pytest.mark.anyio
async def test_pdf_generation_and_cleanup(pdf_tool, tmp_path):
    """Test that PDF is generated and then cleaned up properly."""
    # Use pytest's tmp_path as a writable temp directory for CI safety
    mock_params = Mock()
    mock_params.uuid_for_temp_folder = str(tmp_path / "test-uuid-12345")

    with patch("engine.agent.pdf_generation_tool.get_tracing_span", return_value=mock_params):
        # Generate PDF
        result = await pdf_tool._run_without_trace(markdown_content=MARKDOWN_CONTENT)

        # Verify result structure
        assert result.is_final is True
        assert result.error is None
        assert len(result.messages) == 1
        assert "PDF generated successfully" in result.messages[0].content

        # Get the PDF filename from artifacts
        artifacts = getattr(result, "artifacts", None) or result.__dict__.get("artifacts", {})
        pdf_filename = artifacts.get("pdf_filename")
        assert pdf_filename is not None
        pdf_path = Path(pdf_filename)

        # Verify PDF file exists
        assert pdf_path.exists()
        assert pdf_path.is_file()
        assert pdf_path.suffix == ".pdf"

        # Verify file size is reasonable (not empty)
        assert pdf_path.stat().st_size > 100  # Should be at least 100 bytes

        # Clean up the PDF file
        pdf_path.unlink()
        assert not pdf_path.exists()
