import base64
import zipfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import create_model

from engine.components.component import ComponentAttributes
from engine.components.tools.docx_template import (
    DocxTemplateAgent,
    DocxTemplateInputs,
    TemplateAnalysis,
    _download_and_convert_image,
    _extract_item_fields,
    _read_docx_plaintext,
    _segment_uses_bare_item,
    analyze_docx_template,
    build_context_response_model,
    infer_image_keys,
)
from engine.llm_services.llm_service import CompletionService
from engine.trace.trace_manager import TraceManager


@pytest.fixture
def mock_trace_manager():
    return MagicMock(spec=TraceManager)


@pytest.fixture
def mock_completion_service():
    return MagicMock(spec=CompletionService)


@pytest.fixture
def docx_agent(mock_trace_manager, mock_completion_service):
    return DocxTemplateAgent(
        trace_manager=mock_trace_manager,
        component_attributes=ComponentAttributes(component_instance_name="test"),
        completion_service=mock_completion_service,
    )


@pytest.fixture
def minimal_docx(tmp_path):
    docx_path = tmp_path / "test.docx"
    with zipfile.ZipFile(docx_path, "w") as z:
        z.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/word/document.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            '</Types>',
        )
        z.writestr(
            "word/document.xml",
            '<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            '<w:body><w:p><w:r><w:t>{{ name }}</w:t></w:r></w:p>'
            '<w:p><w:r><w:t>{% for item in items %}{{ item.name }}{% endfor %}</w:t></w:r></w:p>'
            '<w:p><w:r><w:t>{% if condition %}Yes{% endif %}</w:t></w:r></w:p></w:body></w:document>',
        )
        z.writestr(
            "_rels/.rels",
            '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
            'Target="word/document.xml"/>'
            '</Relationships>',
        )
    return docx_path


def test_read_docx_plaintext(minimal_docx):
    result = _read_docx_plaintext(minimal_docx)
    assert "{{ name }}" in result
    assert "{% for item in items %}" in result
    assert "{{ item.name }}" in result
    assert "<w:document>" not in result


def test_extract_item_fields():
    expr = '{{ item.name }} and {{ item.product.sku }} and {{ item["key"] }}'
    fields = _extract_item_fields(expr, "item")
    assert "name" in fields
    assert "product.sku" in fields
    assert "key" in fields
    assert len(fields) == 3


def test_segment_uses_bare_item():
    assert _segment_uses_bare_item("item", "item") is True
    assert _segment_uses_bare_item("(item)", "item") is True
    assert _segment_uses_bare_item("item.name", "item") is False
    assert _segment_uses_bare_item("item|upper", "item") is True


def test_analyze_docx_template(minimal_docx):
    analysis = analyze_docx_template(minimal_docx)
    assert "name" in analysis.variables
    assert "item.name" in analysis.variables
    assert "condition" in analysis.conditions
    assert "items" in analysis.loops
    assert analysis.loops["items"]["list_expr"] == "items"


def test_infer_image_keys():
    analysis = TemplateAnalysis(
        variables={"title", "logo_image", "photo_image_50"},
        conditions=[],
        loops={},
    )
    specs = infer_image_keys(analysis)
    assert specs["logo_image"]["size"] == 25
    assert specs["photo_image_50"]["size"] == 50


def test_build_context_response_model():
    analysis = TemplateAnalysis(
        variables={"name"},
        conditions=["is_active"],
        loops={
            "items": {
                "item_var": "item",
                "list_expr": "items",
                "fields": {"name"},
                "scalar": False,
                "segments": 1,
            },
        },
    )
    ResponseModel = build_context_response_model(analysis, ["logo_image"])
    instance = ResponseModel(
        context={
            "name": "Test",
            "is_active": True,
            "items": [{"name": "Item 1"}],
        },
        images={"logo_image": {"path": "https://example.com/logo.png", "size": 25}},
    )
    assert instance.context.name == "Test"
    assert instance.context.is_active is True
    assert instance.context.items[0].name == "Item 1"
    assert instance.images.logo_image.path == "https://example.com/logo.png"


@patch("engine.components.tools.docx_template.requests.get")
@patch("engine.components.tools.docx_template.Image.open")
@patch("engine.components.tools.docx_template.tempfile.NamedTemporaryFile")
@patch("engine.components.tools.docx_template.Path.unlink")
@patch("engine.components.tools.docx_template.get_output_dir")
def test_download_and_convert_image_http(mock_dir, mock_unlink, mock_temp, mock_img, mock_get, tmp_path):
    mock_get.return_value = MagicMock(content=b"fake", raise_for_status=MagicMock())
    mock_temp.return_value = MagicMock()
    mock_temp.return_value.name = "/tmp/fake.tmp"
    mock_img_obj = MagicMock(format="JPEG", mode="RGB")
    mock_img_obj.__enter__ = MagicMock(return_value=mock_img_obj)
    mock_img_obj.__exit__ = MagicMock(return_value=None)
    mock_img_obj.save = MagicMock()
    mock_img.return_value = mock_img_obj
    mock_dir.return_value = tmp_path
    result = _download_and_convert_image("https://example.com/img.jpg", tmp_path)
    assert result is not None
    assert result.endswith(".jpg")


@patch("engine.components.tools.docx_template.get_output_dir")
def test_download_and_convert_image_local_not_found(mock_dir, tmp_path):
    mock_dir.return_value = tmp_path
    result = _download_and_convert_image("nonexistent.png", tmp_path)
    assert result is None


@pytest.mark.asyncio
async def test_llm_generate_context(docx_agent, mock_completion_service):
    ContextModel = create_model("ContextModel", name=(str, ...))
    ImagesModel = create_model("ImagesModel")
    ResponseModel = create_model("ResponseModel", context=(ContextModel, ...), images=(ImagesModel, ...))
    fake_response = ResponseModel(context=ContextModel(name="Test"), images=ImagesModel())
    mock_completion_service.constrained_complete_with_pydantic_async = AsyncMock(return_value=fake_response)
    result = await docx_agent._llm_generate_context(ResponseModel, "brief", {})
    assert result.context.name == "Test"
    mock_completion_service.constrained_complete_with_pydantic_async.assert_called_once()


@pytest.mark.asyncio
@patch("engine.components.tools.docx_template.analyze_docx_template")
@patch("engine.components.tools.docx_template.build_context_response_model")
@patch("engine.components.tools.docx_template.DocxTemplate")
@patch("engine.components.tools.docx_template.get_output_dir")
@patch("engine.components.tools.docx_template.get_current_span")
async def test_run_without_io_trace_success(
    mock_span,
    mock_dir,
    mock_docx,
    mock_build,
    mock_analyze,
    docx_agent,
    mock_completion_service,
    minimal_docx,
    tmp_path,
):
    mock_span.return_value = MagicMock()
    mock_dir.return_value = tmp_path / "output"
    (tmp_path / "output").mkdir()
    mock_analyze.return_value = TemplateAnalysis(variables={"name"}, conditions=[], loops={})
    ContextModel = create_model("ContextModel", name=(str, ...))
    ImagesModel = create_model("ImagesModel")
    ResponseModel = create_model("ResponseModel", context=(ContextModel, ...), images=(ImagesModel, ...))
    mock_build.return_value = ResponseModel
    mock_completion_service.constrained_complete_with_pydantic_async = AsyncMock(
        return_value=ResponseModel(context=ContextModel(name="Test"), images=ImagesModel())
    )
    mock_docx.return_value = MagicMock()
    inputs = DocxTemplateInputs(
        template_input_path=str(minimal_docx),
        template_information_brief="brief",
        output_filename="out.docx",
    )
    result = await docx_agent._run_without_io_trace(inputs, {})
    assert "Successfully" in result.output


@pytest.mark.asyncio
async def test_run_without_io_trace_no_template(docx_agent):
    with patch("engine.components.tools.docx_template.get_current_span", return_value=MagicMock()):
        inputs = DocxTemplateInputs(
            template_input_path=None,
            template_information_brief="brief",
            output_filename="out.docx",
        )
        result = await docx_agent._run_without_io_trace(inputs, {})
        assert "Either template_input_path or template_base64 must be provided" in result.output


@pytest.mark.asyncio
async def test_run_without_io_trace_base64(mock_trace_manager, mock_completion_service, minimal_docx, tmp_path):
    agent = DocxTemplateAgent(
        trace_manager=mock_trace_manager,
        component_attributes=ComponentAttributes(component_instance_name="test"),
        completion_service=mock_completion_service,
    )
    with open(minimal_docx, "rb") as f:
        template_base64 = base64.b64encode(f.read()).decode("utf-8")
    with (
        patch("engine.components.tools.docx_template.get_current_span", return_value=MagicMock()),
        patch("engine.components.tools.docx_template.get_output_dir", return_value=tmp_path),
        patch(
            "engine.components.tools.docx_template.analyze_docx_template",
            return_value=TemplateAnalysis(variables={"name"}, conditions=[], loops={}),
        ),
        patch("engine.components.tools.docx_template.build_context_response_model") as mock_build,
        patch("engine.components.tools.docx_template.DocxTemplate", return_value=MagicMock()),
    ):
        ContextModel = create_model("ContextModel", name=(str, ...))
        ImagesModel = create_model("ImagesModel")
        ResponseModel = create_model("ResponseModel", context=(ContextModel, ...), images=(ImagesModel, ...))
        mock_build.return_value = ResponseModel
        mock_completion_service.constrained_complete_with_pydantic_async = AsyncMock(
            return_value=ResponseModel(context=ContextModel(name="Test"), images=ImagesModel())
        )
        inputs = DocxTemplateInputs(
            template_base64=template_base64,
            template_information_brief="brief",
            output_filename="out.docx",
        )
        result = await agent._run_without_io_trace(inputs, {})
        assert "Successfully" in result.output
