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
# otherContacts.search only accepts these fields in its readMask (no photos/organizations).
DEFAULT_OTHER_CONTACTS_SEARCH_READ_MASK = "names,emailAddresses,phoneNumbers,metadata"


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
        sync_token: str | None = None,
        other_contacts_sync_token: str | None = None,
    ) -> dict[str, Any]:
        def _build_request(service: Any):
            kwargs: dict[str, Any] = {
                "resourceName": "people/me",
                "personFields": person_fields,
                "pageSize": max_results,
                "requestSyncToken": True,
            }
            if page_token:
                kwargs["pageToken"] = page_token
            if sync_token:
                kwargs["syncToken"] = sync_token
            return service.people().connections().list(**kwargs)

        result = await self._execute(_build_request)
        other_contacts_result = (
            await self.list_other_contacts(
                max_results=max_results,
                read_mask=other_contacts_read_mask,
                page_token=other_contacts_page_token,
                sync_token=other_contacts_sync_token,
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
            "nextSyncToken": result.get("nextSyncToken"),
            "nextOtherContactsSyncToken": (
                other_contacts_result.get("nextOtherContactsSyncToken") if other_contacts_result else None
            ),
            "totalPeople": result.get("totalPeople"),
            "totalItems": result.get("totalItems"),
        }

    async def list_other_contacts(
        self,
        max_results: int = 100,
        read_mask: str = DEFAULT_OTHER_CONTACTS_READ_MASK,
        page_token: str | None = None,
        sync_token: str | None = None,
    ) -> dict[str, Any]:
        def _build_request(service: Any):
            kwargs: dict[str, Any] = {
                "readMask": read_mask,
                "pageSize": max_results,
                "requestSyncToken": True,
            }
            if page_token:
                kwargs["pageToken"] = page_token
            if sync_token:
                kwargs["syncToken"] = sync_token
            return service.otherContacts().list(**kwargs)

        result = await self._execute(_build_request)
        return {
            "otherContacts": result.get("otherContacts", []),
            "nextOtherContactsPageToken": result.get("nextPageToken"),
            "nextOtherContactsSyncToken": result.get("nextSyncToken"),
            "totalSize": result.get("totalSize"),
        }

    async def search_contacts(
        self,
        query: str,
        page_size: int = 10,
        person_fields: str = DEFAULT_PERSON_FIELDS,
        other_contacts_read_mask: str = DEFAULT_OTHER_CONTACTS_SEARCH_READ_MASK,
        warmup_retry_delay_seconds: float = 2.0,
    ) -> dict[str, Any]:
        if not query.strip():
            raise ValueError("query is required")

        def _build_contacts_search(service: Any):
            return service.people().searchContacts(query=query, pageSize=page_size, readMask=person_fields)

        def _build_other_contacts_search(service: Any):
            return service.otherContacts().search(query=query, pageSize=page_size, readMask=other_contacts_read_mask)

        def _unwrap(result: Any) -> list[dict[str, Any]]:
            return [
                item["person"] for item in result.get("results", []) if isinstance(item, dict) and "person" in item
            ]

        async def _run_search() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
            contacts_result, other_contacts_result = await asyncio.gather(
                self._execute(_build_contacts_search),
                self._execute(_build_other_contacts_search),
            )
            return _unwrap(contacts_result), _unwrap(other_contacts_result)

        contacts, other_contacts = await _run_search()
        if not contacts and not other_contacts and warmup_retry_delay_seconds > 0:
            # The People API search endpoints serve from a lazily-built cache; the
            # first request after idle warms it up and may return empty. Per the
            # Google docs, wait a moment and retry once before trusting an empty
            # result. A warm cache (the common case) never pays this delay.
            await asyncio.sleep(warmup_retry_delay_seconds)
            contacts, other_contacts = await _run_search()

        return {
            "contacts": contacts,
            "otherContacts": other_contacts,
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
