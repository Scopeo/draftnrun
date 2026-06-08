"""
Async httpx client for the HubSpot API.

The access token is passed explicitly as an argument
"""

from typing import Any

import httpx

from engine.components.tools.hubspot_mcp.errors import HubSpotAccessTokenRequiredError

_BASE_URL = "https://api.hubapi.com"


class HubSpotClient:
    def __init__(self, access_token: str) -> None:
        if not access_token:
            raise HubSpotAccessTokenRequiredError("access_token is required")
        self._access_token = access_token
        self._headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        self._token_hubspot_metadata: dict[str, Any] | None = None

    async def get_token_hubspot_metadata(self) -> dict:
        if self._token_hubspot_metadata is not None:
            return dict(self._token_hubspot_metadata)

        async with httpx.AsyncClient(base_url=_BASE_URL, timeout=30.0) as client:
            response = await client.get(f"/oauth/v1/access-tokens/{self._access_token}")

        if not response.is_success:
            try:
                detail = response.json()
            except Exception:
                detail = response.text
            raise RuntimeError(f"HubSpot API error {response.status_code}: {detail}")

        self._token_hubspot_metadata = dict(response.json())
        return dict(self._token_hubspot_metadata)

    async def request(self, method: str, path: str, **kwargs) -> dict:
        async with httpx.AsyncClient(base_url=_BASE_URL, headers=self._headers, timeout=30.0) as client:
            response = await getattr(client, method)(path, **kwargs)

        if not response.is_success:
            try:
                detail = response.json()
            except Exception:
                detail = response.text
            raise RuntimeError(f"HubSpot API error {response.status_code}: {detail}")

        if response.status_code == 204:
            return {}

        return response.json()
