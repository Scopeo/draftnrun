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
