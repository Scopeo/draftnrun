import logging
from typing import Any

import httpx

from settings import settings

LOGGER = logging.getLogger(__name__)


class NangoClientError(Exception):
    def __init__(self, message: str, status_code: int | None = None, response_body: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


class NangoClient:
    def __init__(
        self,
        base_url: str | None = None,
        secret_key: str | None = None,
    ):
        self.base_url = (base_url or settings.NANGO_INTERNAL_URL or "").rstrip("/")
        self.secret_key = secret_key or settings.NANGO_SECRET_KEY

        if not self.base_url:
            raise ValueError("Nango base URL is not configured")
        if not self.secret_key:
            raise ValueError("Nango secret key is not configured")

        self.client = httpx.AsyncClient()

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.secret_key}",
            "Content-Type": "application/json",
        }

    async def health_check(self) -> bool:
        try:
            response = await self.client.get(f"{self.base_url}/health", timeout=5.0)
            return response.status_code == 200
        except Exception as e:
            LOGGER.warning(f"Nango health check failed: {e}")
            return False

    async def create_connect_session(
        self,
        end_user_id: str,
        end_user_email: str | None = None,
        end_user_display_name: str | None = None,
        allowed_integrations: list[str] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "end_user": {
                "id": end_user_id,
            }
        }
        if end_user_email:
            payload["end_user"]["email"] = end_user_email
        if end_user_display_name:
            payload["end_user"]["display_name"] = end_user_display_name
        if allowed_integrations:
            payload["allowed_integrations"] = allowed_integrations

        response = await self.client.post(
            f"{self.base_url}/connect/sessions",
            headers=self._headers(),
            json=payload,
            timeout=10.0,
        )

        if response.status_code not in (200, 201):
            raise NangoClientError(
                f"Failed to create connect session: {response.text}",
                status_code=response.status_code,
                response_body=response.text,
            )
        return response.json().get("data", {})

    async def list_connections(
        self,
        provider_config_key: str | None = None,
        end_user_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        List connections.

        NOTE: Nango v0.69 API is strict and rejects query params it doesn't recognize.
        We fetch ALL connections and filter client-side (in Python) to avoid 400 Errors.
        """
        response = await self.client.get(
            f"{self.base_url}/connection",
            headers=self._headers(),
            timeout=10.0,
        )

        if response.status_code != 200:
            raise NangoClientError(
                f"Failed to list connections: {response.text}",
                status_code=response.status_code,
                response_body=response.text,
            )

        # CRITICAL: Nango v0.69 (Self-Hosted) throws 400 "unrecognized_keys"
        # if we try to filter via query params (e.g. ?provider_config_key=...).
        # We MUST fetch all connections and filter in memory until we upgrade Nango.
        all_connections = response.json().get("connections", [])

        # 2. Filter in memory
        filtered = all_connections

        if provider_config_key:
            filtered = [c for c in filtered if c.get("provider_config_key") == provider_config_key]

        if end_user_id:
            # Check both root level 'end_user_id' and nested 'end_user.id' for compatibility
            filtered = [
                c
                for c in filtered
                if c.get("end_user_id") == end_user_id or c.get("end_user", {}).get("id") == end_user_id
            ]

        return filtered

    async def get_connection(
        self,
        provider_config_key: str,
        connection_id: str,
    ) -> dict[str, Any] | None:
        response = await self.client.get(
            f"{self.base_url}/connection/{connection_id}",
            headers=self._headers(),
            params={"provider_config_key": provider_config_key},
            timeout=10.0,
        )

        if response.status_code == 404:
            return None
        if response.status_code != 200:
            raise NangoClientError(
                f"Failed to get connection: {response.text}",
                status_code=response.status_code,
                response_body=response.text,
            )
        return response.json()

    async def delete_connection(
        self,
        provider_config_key: str,
        connection_id: str,
    ) -> bool:
        response = await self.client.delete(
            f"{self.base_url}/connection/{connection_id}",
            headers=self._headers(),
            params={"provider_config_key": provider_config_key},
            timeout=10.0,
        )
        if response.status_code == 404:
            return False
        if response.status_code not in (200, 204):
            raise NangoClientError(
                f"Failed to delete connection: {response.text}",
                status_code=response.status_code,
                response_body=response.text,
            )
        return True

    async def proxy_request(
        self,
        endpoint: str,
        provider_config_key: str,
        connection_id: str,
        method: str = "GET",
        data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        retries: int = 0,
    ) -> httpx.Response:
        headers = self._headers()
        headers["Connection-Id"] = connection_id
        headers["Provider-Config-Key"] = provider_config_key
        if retries > 0:
            headers["Retries"] = str(retries)

        url = f"{self.base_url}/proxy{endpoint}"

        response = await self.client.request(
            method=method.upper(),
            url=url,
            headers=headers,
            json=data if data else None,
            params=params,
            timeout=30.0,
        )
        return response

    async def close(self) -> None:
        await self.client.aclose()


_nango_client: NangoClient | None = None


def get_nango_client() -> NangoClient:
    global _nango_client
    if _nango_client is None:
        _nango_client = NangoClient()
    return _nango_client
