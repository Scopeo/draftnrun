"""HTTP client for Draft'n Run backend API calls.

Thin async wrapper around httpx.AsyncClient that injects the Supabase JWT,
handles errors, and trims oversized responses.
"""

import json
import logging
from typing import Any

import httpx

from mcp_server.settings import settings

logger = logging.getLogger(__name__)

_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            base_url=settings.BACKEND_URL,
            timeout=settings.MCP_REQUEST_TIMEOUT,
        )
    return _client


def _trim_response(data: Any) -> Any:
    raw = json.dumps(data, default=str)
    if len(raw) <= settings.MCP_RESPONSE_MAX_SIZE:
        return data

    max_size = settings.MCP_RESPONSE_MAX_SIZE
    meta: dict[str, Any] = {
        "_truncated": True,
        "_note": f"Response exceeded {max_size} chars and was trimmed.",
    }

    if isinstance(data, list):
        meta["_total_items"] = len(data)
        meta["_included_items"] = 0
        subset: list = []
        for item in data:
            tentative = {**meta, "partial_data": subset + [item], "_included_items": len(subset) + 1}
            if len(json.dumps(tentative, default=str)) > max_size:
                break
            subset.append(item)
        if subset:
            meta["partial_data"] = subset
            meta["_included_items"] = len(subset)
        return meta

    if isinstance(data, dict):
        subset_dict: dict = {}
        for key, value in data.items():
            tentative = {**meta, "partial_data": {**subset_dict, key: value}}
            if len(json.dumps(tentative, default=str)) > max_size:
                break
            subset_dict[key] = value
        if subset_dict:
            meta["partial_data"] = subset_dict
        return meta

    return meta


def _make_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _extract_error_detail(response: httpx.Response) -> str:
    """Best-effort extraction of the backend's error detail from an HTTP error response."""
    try:
        body = response.json()
        if isinstance(body, dict):
            return body.get("detail", "")
    except (json.JSONDecodeError, ValueError):
        pass
    text = response.text[:300].strip()
    return text if text else ""


async def _handle_response(response: httpx.Response, *, trim: bool = True) -> Any:
    if response.status_code == 204:
        return {"status": "ok"}

    if response.status_code == 401:
        raise ToolError(
            "Authentication failed. Your session may have expired — reconnect to refresh. "
            "Next step: check your MCP client's server status, then call get_current_context() "
            "to verify your session."
        )

    if response.status_code == 403:
        detail = _extract_error_detail(response)
        base = "Permission denied."
        hint = (
            " Next step: call get_current_context() to check your role, "
            "then see docs://getting-started for the role hierarchy."
        )
        if detail:
            raise ToolError(f"{base} {detail}{hint}")
        raise ToolError(f"{base} You may lack the required role for this operation.{hint}")

    if response.status_code == 404:
        detail = _extract_error_detail(response)
        raise ToolError(
            f"Resource not found.{f' {detail}' if detail else ''} "
            "Next step: verify the ID came from a list_*/get_* call in this session — "
            "never reuse IDs across projects or orgs."
        )

    if response.status_code == 429:
        retry_after = response.headers.get("Retry-After", "unknown")
        raise ToolError(f"Rate limited by backend. Retry after {retry_after}s.")

    if response.status_code >= 400:
        detail = ""
        try:
            body = response.json()
            detail = body.get("detail", str(body)) if isinstance(body, dict) else str(body)
        except (json.JSONDecodeError, ValueError):
            detail = response.text[:500]
        raise ToolError(f"Backend error {response.status_code}: {detail}")

    try:
        data = response.json()
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("Backend returned a non-JSON success response: %s", exc)
        data = response.text
    return _trim_response(data) if trim else data


class ToolError(Exception):
    pass


class DraftnrunClient:
    async def get(self, path: str, token: str, *, trim: bool = True, **params: Any) -> Any:
        client = _get_client()
        response = await client.get(path, headers=_make_headers(token), params=params or None)
        return await _handle_response(response, trim=trim)

    async def get_raw(self, path: str, token: str, **params: Any) -> str:
        """Return the raw response text (for non-JSON endpoints like CSV export)."""
        client = _get_client()
        response = await client.get(path, headers=_make_headers(token), params=params or None)
        if response.status_code >= 400:
            await _handle_response(response)
        return response.text

    async def post(self, path: str, token: str, json: dict | None = None, trim: bool = True, **params: Any) -> Any:
        client = _get_client()
        response = await client.post(path, headers=_make_headers(token), json=json, params=params or None)
        return await _handle_response(response, trim=trim)

    async def post_file(
        self, path: str, token: str, *,
        file_content: bytes, filename: str, field_name: str = "file",
        content_type: str = "text/csv",
        trim: bool = True, **params: Any,
    ) -> Any:
        """Upload a file via multipart form data (for CSV import, etc.)."""
        client = _get_client()
        response = await client.post(
            path,
            headers=_make_headers(token),
            files={field_name: (filename, file_content, content_type)},
            params=params or None,
        )
        return await _handle_response(response, trim=trim)

    async def put(self, path: str, token: str, json: dict | None = None, *, trim: bool = True) -> Any:
        client = _get_client()
        response = await client.put(path, headers=_make_headers(token), json=json)
        return await _handle_response(response, trim=trim)

    async def patch(self, path: str, token: str, json: dict | None = None, *, trim: bool = True) -> Any:
        client = _get_client()
        response = await client.patch(path, headers=_make_headers(token), json=json)
        return await _handle_response(response, trim=trim)

    async def delete(
        self, path: str, token: str, json: dict | list | None = None,
        trim: bool = True, **params: Any,
    ) -> Any:
        client = _get_client()
        response = await client.request(
            "DELETE", path, headers=_make_headers(token), json=json, params=params or None,
        )
        return await _handle_response(response, trim=trim)


api = DraftnrunClient()
