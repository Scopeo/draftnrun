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
async def test_handle_400_returns_actionable_message():
    body = json.dumps({"detail": "payload is missing required field: name"})
    response = httpx.Response(400, text=body, headers={"content-type": "application/json"})

    with pytest.raises(ToolError, match="Invalid request.*check parameter types"):
        await _handle_response(response)


@pytest.mark.asyncio
async def test_handle_409_returns_conflict_guidance():
    body = json.dumps({"detail": "Graph was modified by another client"})
    response = httpx.Response(409, text=body, headers={"content-type": "application/json"})

    with pytest.raises(ToolError, match="Conflict.*re-fetch the resource.*retry"):
        await _handle_response(response)


@pytest.mark.asyncio
async def test_handle_422_formats_validation_errors():
    body = json.dumps(
        {
            "detail": [
                {"loc": ["body", "name"], "msg": "Field required"},
                {"loc": ["body", "page_size"], "msg": "Input should be greater than 0"},
            ]
        }
    )
    response = httpx.Response(422, text=body, headers={"content-type": "application/json"})

    with pytest.raises(ToolError, match=r"Input validation failed:[\s\S]*body\.name: Field required"):
        await _handle_response(response)


@pytest.mark.asyncio
async def test_handle_422_with_blank_detail_falls_back_to_default_message():
    body = json.dumps({"detail": "  \n  "})
    response = httpx.Response(422, text=body, headers={"content-type": "application/json"})

    with pytest.raises(ToolError, match="No error detail returned"):
        await _handle_response(response)
