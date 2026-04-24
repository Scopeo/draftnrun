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
    """Best-effort extraction of the backend's error detail from an HTTP error response.

    Always returns a stripped string (empty if no meaningful detail found).
    """
    try:
        body = response.json()
        if isinstance(body, dict):
            detail = body.get("detail", "")
            return detail.strip() if isinstance(detail, str) else str(detail).strip()
    except (json.JSONDecodeError, ValueError):
        pass
    text = response.text[:300].strip()
    return text if text else ""


def _format_validation_errors(response: httpx.Response) -> str:
    """Format FastAPI/Pydantic validation errors as 'field.path: message' lines."""
    try:
        body = response.json()
    except (json.JSONDecodeError, ValueError):
        body = None

    if isinstance(body, dict):
        detail = body.get("detail")
        if isinstance(detail, list):
            lines: list[str] = []
            for item in detail:
                if not isinstance(item, dict):
                    continue
                msg = item.get("msg")
                loc = item.get("loc")
                if not isinstance(msg, str) or not msg.strip():
                    continue
                if isinstance(loc, (list, tuple)) and loc:
                    path = ".".join(str(part) for part in loc)
                else:
                    path = "input"
                lines.append(f"{path}: {msg.strip()}")
            if lines:
                return "\n".join(lines)

    fallback = _extract_error_detail(response)
    if fallback:
        return fallback
    return f"No error detail returned by the server (HTTP {response.status_code})"


async def _handle_response(response: httpx.Response, *, trim: bool = True) -> Any:
    if response.status_code == 204:
        return {"status": "ok"}

    try:
        req = response.request
        request_context = f" [{req.method} {req.url.path}]"
    except RuntimeError:
        request_context = ""

    if response.status_code == 401:
        raise ToolError(
            f"Authentication failed{request_context}. Your session may have expired — reconnect to refresh. "
            "Next step: check your MCP client's server status, then call get_current_context() "
            "to verify your session."
        )

    if response.status_code == 403:
        detail = _extract_error_detail(response)
        base = f"Permission denied{request_context}."
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
            f"Resource not found{request_context}.{f' {detail}' if detail else ''} "
            "Next step: verify the ID came from a list_*/get_* call in this session — "
            "never reuse IDs across projects or orgs."
        )

    if response.status_code == 400:
        detail = _extract_error_detail(response)
        raise ToolError(
            f"Invalid request{request_context}.{f' {detail}' if detail else ''} "
            "Next step: check parameter types and required fields in the tool's docstring."
        )

    if response.status_code == 409:
        detail = _extract_error_detail(response)
        raise ToolError(
            f"Conflict{request_context}.{f' {detail}' if detail else ''} "
            "Next step: re-fetch the resource (e.g. get_graph) to get the latest state, "
            "re-apply your changes, and retry."
        )

    if response.status_code == 422:
        detail = _format_validation_errors(response)
        raise ToolError(
            f"Input validation failed{request_context}:\n{detail}\n"
            "Next step: fix the values above and retry."
        )

    if response.status_code == 429:
        retry_after = response.headers.get("Retry-After", "unknown")
        raise ToolError(f"Rate limited by backend{request_context}. Retry after {retry_after}s.")

    if response.status_code == 500:
        detail = _extract_error_detail(response)
        raise ToolError(
            f"The backend hit an unexpected error{request_context}. "
            "This is not caused by your input — retry the call. "
            f"If it persists, the issue is server-side.{f' Detail: {detail}' if detail else ''}"
        )

    if response.status_code == 502:
        raise ToolError(
            f"The backend is temporarily unreachable (gateway error){request_context}. "
            "Retry in a few seconds."
        )

    if response.status_code == 503:
        raise ToolError(
            f"The backend is temporarily unavailable{request_context}. "
            "Retry in a few seconds."
        )

    if response.status_code >= 400:
        detail = ""
        try:
            body = response.json()
            detail = body.get("detail", str(body)) if isinstance(body, dict) else str(body)
        except (json.JSONDecodeError, ValueError):
            detail = response.text[:500]
        if isinstance(detail, str):
            detail = detail.strip()
        if not detail:
            detail = f"No error detail returned by the server (HTTP {response.status_code})"
        raise ToolError(f"Backend error {response.status_code}{request_context}: {detail}")

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
