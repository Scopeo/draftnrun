"""
Async httpx client for the HubSpot API.

The access token is passed explicitly as an argument
"""

import httpx

from engine.components.tools.hubspot_mcp.errors import HubSpotAccessTokenRequiredError

_BASE_URL = "https://api.hubapi.com"


class HubSpotClient:
    def __init__(self, access_token: str) -> None:
        if not access_token:
            raise HubSpotAccessTokenRequiredError("access_token is required")
        self._headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

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
