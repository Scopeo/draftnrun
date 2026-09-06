import json

import httpx
import pytest

from mcp_server.client import ToolError, _extract_error_detail, _handle_response


@pytest.mark.asyncio
async def test_handle_response_accepts_non_json_success_body():
    response = httpx.Response(200, text="ok")

    result = await _handle_response(response)

    assert result == "ok"


def test_extract_error_detail_from_json():
    body = json.dumps({"detail": "Org does not have catalog access"})
    response = httpx.Response(403, text=body, headers={"content-type": "application/json"})

    assert _extract_error_detail(response) == "Org does not have catalog access"


def test_extract_error_detail_from_plain_text():
    response = httpx.Response(403, text="Forbidden by policy")

    assert _extract_error_detail(response) == "Forbidden by policy"


def test_extract_error_detail_empty_body():
    response = httpx.Response(403, text="")

    assert _extract_error_detail(response) == ""


@pytest.mark.asyncio
async def test_handle_403_includes_backend_detail():
    body = json.dumps({"detail": "Component catalog requires early_access tier"})
    response = httpx.Response(403, text=body, headers={"content-type": "application/json"})

    with pytest.raises(ToolError, match="Component catalog requires early_access tier"):
        await _handle_response(response)


@pytest.mark.asyncio
async def test_handle_403_falls_back_to_generic_message():
    response = httpx.Response(403, text="")

    with pytest.raises(ToolError, match="You may lack the required role"):
        await _handle_response(response)


@pytest.mark.asyncio
async def test_post_trim_false_returns_full_data():
    big_data = {"key": "x" * 100000}
    body = json.dumps(big_data)
    response = httpx.Response(200, text=body, headers={"content-type": "application/json"})
    result = await _handle_response(response, trim=False)
    assert result == big_data
    assert "_truncated" not in str(result)


@pytest.mark.asyncio
async def test_handle_404_includes_backend_detail():
    body = json.dumps({"detail": "Project abc-123 not found"})
    response = httpx.Response(404, text=body, headers={"content-type": "application/json"})

    with pytest.raises(ToolError, match="Project abc-123 not found"):
        await _handle_response(response)


@pytest.mark.asyncio
async def test_handle_500_returns_actionable_message():
    body = json.dumps({"detail": "Internal Server Error"})
    response = httpx.Response(500, text=body, headers={"content-type": "application/json"})

    with pytest.raises(ToolError, match="unexpected error.*not caused by your input"):
        await _handle_response(response)


@pytest.mark.asyncio
async def test_handle_502_returns_gateway_message():
    response = httpx.Response(502, text="Bad Gateway")

    with pytest.raises(ToolError, match="temporarily unreachable"):
        await _handle_response(response)


@pytest.mark.asyncio
async def test_handle_503_returns_unavailable_message():
    response = httpx.Response(503, text="Service Unavailable")

    with pytest.raises(ToolError, match="temporarily unavailable"):
        await _handle_response(response)


@pytest.mark.asyncio
async def test_handle_error_includes_request_path():
    request = httpx.Request("PUT", "http://example.com/projects/123/graph/456")
    response = httpx.Response(500, text="crash", request=request)

    with pytest.raises(ToolError, match=r"\[PUT /projects/123/graph/456\]"):
        await _handle_response(response)


@pytest.mark.asyncio
async def test_handle_generic_4xx_with_blank_detail():
    response = httpx.Response(422, text="")

    with pytest.raises(ToolError, match="No error detail returned"):
        await _handle_response(response)


@pytest.mark.asyncio
async def test_handle_generic_4xx_with_whitespace_only_detail():
    body = json.dumps({"detail": "  \n  "})
    response = httpx.Response(422, text=body, headers={"content-type": "application/json"})

    with pytest.raises(ToolError, match="No error detail returned"):
        await _handle_response(response)


# --- _trim_response (the 50KB guardrail) ---

from mcp_server.client import _trim_response  # noqa: E402
from mcp_server.settings import settings  # noqa: E402


@pytest.fixture
def small_max_size(monkeypatch):
    monkeypatch.setattr(settings, "MCP_RESPONSE_MAX_SIZE", 400)


def test_trim_passes_small_responses_through(small_max_size):
    data = {"a": 1}
    assert _trim_response(data) is data


def test_trim_list_keeps_prefix_and_reports_counts(small_max_size):
    data = [{"i": i, "pad": "x" * 50} for i in range(20)]

    result = _trim_response(data)

    assert result["_truncated"] is True
    assert result["_total_items"] == 20
    assert 0 < result["_included_items"] < 20
    assert result["partial_data"] == data[: result["_included_items"]]
    assert len(json.dumps(result, default=str)) <= settings.MCP_RESPONSE_MAX_SIZE + 100


def test_trim_list_first_item_too_big_returns_meta_only(small_max_size):
    data = [{"huge": "x" * 1000}, {"small": 1}]

    result = _trim_response(data)

    assert result["_truncated"] is True
    assert result["_included_items"] == 0
    assert "partial_data" not in result


def test_trim_dict_keeps_prefix_of_keys(small_max_size):
    data = {f"key_{i}": "v" * 50 for i in range(20)}

    result = _trim_response(data)

    assert result["_truncated"] is True
    keys = list(result["partial_data"].keys())
    assert 0 < len(keys) < 20
    assert keys == [f"key_{i}" for i in range(len(keys))]


def test_trim_oversized_scalar_returns_meta(small_max_size):
    result = _trim_response("y" * 1000)

    assert result["_truncated"] is True
    assert "partial_data" not in result


def test_tool_error_is_fastmcp_tool_error():
    from fastmcp.exceptions import ToolError as FastMCPToolError

    assert issubclass(ToolError, FastMCPToolError)


@pytest.mark.asyncio
async def test_tool_errors_carry_status_code_and_transience():
    for status, transient in [(401, False), (403, False), (404, False), (429, True), (500, True), (503, True)]:
        response = httpx.Response(status, text="")
        with pytest.raises(ToolError) as exc_info:
            await _handle_response(response)
        assert exc_info.value.status_code == status
        assert exc_info.value.is_transient is transient

    assert ToolError("no status").is_transient is True
