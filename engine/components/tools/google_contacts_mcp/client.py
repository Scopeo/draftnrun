"""
Thin async client for the Google People API contacts surface.

Uses the Google API Python client under the hood, but wraps calls in
asyncio.to_thread so the FastMCP server stays non-blocking.

This module is imported by the MCP stdio subprocess (server.py), so it must NOT
import anything from ada_backend/ - the subprocess runs with a minimal
environment and ada_backend.database.models would crash on missing FERNET_KEY.
"""

import asyncio
from collections.abc import Callable
from typing import Any

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

DEFAULT_PERSON_FIELDS = "names,emailAddresses,phoneNumbers,organizations,photos,metadata"
DEFAULT_OTHER_CONTACTS_READ_MASK = "names,emailAddresses,phoneNumbers,photos,metadata"


class GoogleContactsClient:
    def __init__(self, access_token: str) -> None:
        if not access_token:
            raise ValueError("access_token is required")
        self._access_token = access_token

    def _build_service(self) -> Any:
        creds = Credentials(token=self._access_token)
        return build("people", "v1", credentials=creds)

    async def _execute(self, request_builder: Callable[[Any], Any]) -> Any:
        def _call():
            service = self._build_service()
            return request_builder(service).execute()

        return await asyncio.to_thread(_call)

    async def list_contacts(
        self,
        max_results: int = 100,
        person_fields: str = DEFAULT_PERSON_FIELDS,
        page_token: str | None = None,
        include_other_contacts: bool = True,
        other_contacts_page_token: str | None = None,
        other_contacts_read_mask: str = DEFAULT_OTHER_CONTACTS_READ_MASK,
    ) -> dict[str, Any]:
        def _build_request(service: Any):
            kwargs: dict[str, Any] = {
                "resourceName": "people/me",
                "personFields": person_fields,
                "pageSize": max_results,
            }
            if page_token:
                kwargs["pageToken"] = page_token
            return service.people().connections().list(**kwargs)

        result = await self._execute(_build_request)
        other_contacts_result = (
            await self.list_other_contacts(
                max_results=max_results,
                read_mask=other_contacts_read_mask,
                page_token=other_contacts_page_token,
            )
            if include_other_contacts
            else None
        )
        return {
            "contacts": result.get("connections", []),
            "otherContacts": other_contacts_result["otherContacts"] if other_contacts_result else [],
            "nextPageToken": result.get("nextPageToken"),
            "nextOtherContactsPageToken": (
                other_contacts_result.get("nextOtherContactsPageToken") if other_contacts_result else None
            ),
            "totalPeople": result.get("totalPeople"),
            "totalItems": result.get("totalItems"),
        }

    async def list_other_contacts(
        self,
        max_results: int = 100,
        read_mask: str = DEFAULT_OTHER_CONTACTS_READ_MASK,
        page_token: str | None = None,
    ) -> dict[str, Any]:
        def _build_request(service: Any):
            kwargs: dict[str, Any] = {
                "readMask": read_mask,
                "pageSize": max_results,
            }
            if page_token:
                kwargs["pageToken"] = page_token
            return service.otherContacts().list(**kwargs)

        result = await self._execute(_build_request)
        return {
            "otherContacts": result.get("otherContacts", []),
            "nextOtherContactsPageToken": result.get("nextPageToken"),
            "totalSize": result.get("totalSize"),
        }

    async def get_contact(
        self,
        resource_name: str,
        person_fields: str = DEFAULT_PERSON_FIELDS,
    ) -> dict[str, Any]:
        if not resource_name.startswith("people/"):
            raise ValueError("resource_name must start with 'people/'")

        def _build_request(service: Any):
            return service.people().get(resourceName=resource_name, personFields=person_fields)

        return await self._execute(_build_request)
