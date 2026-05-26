import json

import httpx

from engine.components.tools.notion_mcp.errors import NotionAccessTokenRequiredError

_BASE_URL = "https://api.notion.com"
_NOTION_VERSION = "2026-03-11"


class NotionClient:
    def __init__(self, access_token: str) -> None:
        if not access_token:
            raise NotionAccessTokenRequiredError("access_token is required")
        self._access_token = access_token
        self._headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "Notion-Version": _NOTION_VERSION,
        }

    async def request(self, method: str, path: str, **kwargs) -> dict:
        async with httpx.AsyncClient(base_url=_BASE_URL, headers=self._headers, timeout=30.0) as client:
            response = await getattr(client, method)(path, **kwargs)

        if not response.is_success:
            try:
                detail = response.json()
            except (json.JSONDecodeError, ValueError):
                detail = response.text
            raise RuntimeError(f"Notion API error {response.status_code}: {detail}")

        if response.status_code == 204:
            return {}

        return response.json()
