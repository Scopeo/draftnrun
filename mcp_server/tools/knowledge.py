"""Knowledge base and source management tools.

Safe default: inspect existing sources/documents first. Documents are logical
groups of ingested chunks, not guaranteed original binary files. Mutation tools
have important limitations; see `docs://file-management`.
"""

from __future__ import annotations

from typing import Optional

from fastmcp import FastMCP

from mcp_server.client import api
from mcp_server.context import require_role
from mcp_server.tools._factory import Param, ToolSpec, register_proxy_tools
from mcp_server.tools.context_tools import _get_auth

_VALID_SOURCE_TYPES = ("website", "database")

_WEBSITE_REQUIRED = ("url",)
_DATABASE_REQUIRED = ("source_db_url", "source_table_name", "id_column_name", "text_column_names")

_SOURCE_ID = Param("source_id", str, description="The source ID.")
_DOC_ID = Param("document_id", str, description="The document ID.")

PROXY_SPECS: list[ToolSpec] = [
    # --- Sources ---
    ToolSpec(
        name="list_sources",
        description="List all knowledge sources in the active organization.",
        method="get",
        path="/sources/{org_id}",
        scope="org",
        return_annotation=list,
    ),
    ToolSpec(
        name="update_source",
        description=(
            "Re-trigger ingestion for an existing knowledge source.\n\n"
            "This does NOT accept configuration changes — the `source_data` parameter "
            "is ignored by the backend. It re-runs ingestion using the stored source "
            "definition (URL, DB connection, files, etc.).\n\n"
            "To change source configuration (e.g. URL, limit, crawl depth), use the "
            "web product at https://app.draftnrun.com."
        ),
        method="post",
        path="/sources/{org_id}/{source_id}",
        scope="org",
        path_params=(_SOURCE_ID,),
        body_param=Param("source_data", dict, description="Ignored by backend. Kept for API compatibility."),
    ),
    ToolSpec(
        name="delete_source",
        description=(
            "Delete a knowledge source. Requires developer role or above.\n\n"
            "Tip: call check_source_usage first to see which projects reference it."
        ),
        method="delete",
        path="/sources/{org_id}/{source_id}",
        scope="role",
        roles=("developer", "admin", "super_admin"),
        path_params=(_SOURCE_ID,),
    ),
    ToolSpec(
        name="check_source_usage",
        description="Check which projects/components use a knowledge source.",
        method="get",
        path="/organizations/{org_id}/sources/{source_id}/usage",
        scope="org",
        path_params=(_SOURCE_ID,),
    ),
    # --- Documents ---
    ToolSpec(
        name="list_documents",
        description=(
            "List logical documents in a knowledge source.\n\n"
            "Documents are grouped by ingested `file_id` / document identifier, not "
            "guaranteed original files."
        ),
        method="get",
        path="/knowledge/organizations/{org_id}/sources/{source_id}/documents",
        scope="org",
        path_params=(_SOURCE_ID,),
        return_annotation=list,
    ),
    ToolSpec(
        name="get_document",
        description=(
            "Get a logical document with its chunks.\n\n"
            "This returns ingested chunk data for the document identifier, not a "
            "downloadable original binary file."
        ),
        method="get",
        path="/knowledge/organizations/{org_id}/sources/{source_id}/documents/{document_id}",
        scope="org",
        path_params=(_SOURCE_ID, _DOC_ID),
    ),
    ToolSpec(
        name="delete_document",
        description=(
            "Delete a logical document from a knowledge source.\n\n"
            "Current backend deletion removes rows by document/file ID, but vector "
            "cleanup is not guaranteed. Treat as destructive and confirm user intent "
            "first."
        ),
        method="delete",
        path="/knowledge/organizations/{org_id}/sources/{source_id}/documents/{document_id}",
        scope="role",
        roles=("developer", "admin", "super_admin"),
        path_params=(_SOURCE_ID, _DOC_ID),
    ),
]


def _validate_website_config(config: dict) -> dict:
    """Validate and normalize website source config into IngestionTaskQueue shape."""
    missing = [k for k in _WEBSITE_REQUIRED if not config.get(k)]
    if missing:
        raise ValueError(f"Website source requires: {', '.join(missing)}")
    return {
        "url": config["url"],
        "follow_links": config.get("follow_links", True),
        "max_depth": config.get("max_depth", 1),
        "limit": config.get("limit", 100),
        "include_paths": config.get("include_paths"),
        "exclude_paths": config.get("exclude_paths"),
        "include_tags": config.get("include_tags"),
        "exclude_tags": config.get("exclude_tags"),
        "chunk_size": config.get("chunk_size"),
        "chunk_overlap": config.get("chunk_overlap"),
        "document_reading_mode": config.get("document_reading_mode"),
    }


def _validate_database_config(config: dict) -> dict:
    """Validate and normalize database source config into IngestionTaskQueue shape."""
    missing = [k for k in _DATABASE_REQUIRED if not config.get(k)]
    if missing:
        raise ValueError(f"Database source requires: {', '.join(missing)}")
    return {
        "source_db_url": config["source_db_url"],
        "source_table_name": config["source_table_name"],
        "id_column_name": config["id_column_name"],
        "text_column_names": config["text_column_names"],
        "source_schema_name": config.get("source_schema_name"),
        "metadata_column_names": config.get("metadata_column_names"),
        "timestamp_column_name": config.get("timestamp_column_name"),
        "url_pattern": config.get("url_pattern"),
        "chunk_size": config.get("chunk_size"),
        "chunk_overlap": config.get("chunk_overlap"),
        "update_existing": config.get("update_existing", False),
        "query_filter": config.get("query_filter"),
        "timestamp_filter": config.get("timestamp_filter"),
    }


_CONFIG_VALIDATORS = {
    "website": _validate_website_config,
    "database": _validate_database_config,
}


def register(mcp: FastMCP) -> None:
    register_proxy_tools(mcp, PROXY_SPECS)

    @mcp.tool()
    async def create_source(
        source_type: str,
        config: dict,
        name: Optional[str] = None,
    ) -> dict:
        """Create a new knowledge source and trigger its first ingestion.

        Supported source types via MCP: ``website``, ``database``.
        (``local`` and ``google_drive`` require the web UI.)

        The backend creates the source record, provisions infrastructure
        (DB table, Qdrant collection), and starts ingestion automatically.

        Args:
            source_type: One of "website" or "database".
            config: Type-specific configuration dict.
                For website:
                  - url (str, required): Starting URL to crawl.
                  - follow_links (bool, default True): Follow links on pages.
                  - max_depth (int, default 1): Crawl depth.
                  - limit (int, default 100): Max pages to crawl.
                  - include_paths (list[str]): URL pathname regex patterns to include.
                  - exclude_paths (list[str]): URL pathname regex patterns to exclude.
                  - include_tags (list[str]): HTML tags to keep.
                  - exclude_tags (list[str]): HTML tags to strip.
                  - chunk_size (int): Override default chunk size (1024).
                  - chunk_overlap (int): Override default chunk overlap (0).
                For database:
                  - source_db_url (str, required): Connection string.
                  - source_table_name (str, required): Table to ingest.
                  - id_column_name (str, required): Row identifier column.
                  - text_column_names (list[str], required): Columns to index.
                  - source_schema_name (str): DB schema name.
                  - metadata_column_names (list[str]): Columns carried as metadata.
                  - timestamp_column_name (str): For incremental ingestion.
                  - chunk_size (int): Override default chunk size.
                  - chunk_overlap (int): Override default chunk overlap.
                  - update_existing (bool, default False): Re-ingest existing rows.
                  - query_filter (str): SQL WHERE filter.
                  - timestamp_filter (str): Timestamp-based filter.
            name: Human-readable source name. Auto-generated if omitted.
        """
        if source_type not in _VALID_SOURCE_TYPES:
            raise ValueError(
                f"source_type must be one of {_VALID_SOURCE_TYPES}. "
                f"Got '{source_type}'. For 'local' or 'google_drive', use the web UI."
            )

        validator = _CONFIG_VALIDATORS[source_type]
        source_attributes = validator(config)

        if not name:
            if source_type == "website":
                name = f"Website: {config['url'][:60]}"
            else:
                name = f"Database: {config['source_table_name']}"

        jwt, user_id = _get_auth()
        org = await require_role(user_id, "developer", "admin", "super_admin")

        payload = {
            "source_name": name,
            "source_type": source_type,
            "status": "pending",
            "source_attributes": {k: v for k, v in source_attributes.items() if v is not None},
        }

        task_id = await api.post(f"/ingestion_task/{org['org_id']}", jwt, json=payload)

        return {
            "status": "ok",
            "task_id": str(task_id),
            "source_type": source_type,
            "source_name": name,
            "message": (
                "Ingestion task created. The source will appear in list_sources "
                "once ingestion starts processing."
            ),
        }

    @mcp.tool()
    async def update_document_chunks(
        source_id: str,
        document_id: str,
        chunks: list[dict],
        confirm_full_replacement: bool = False,
    ) -> dict:
        """Replace all chunks of a document with caution.

        This is not a safe partial-patch API. The current backend sync is
        source-scoped, so omitted chunks can affect other vectors in the same
        source. Use only when the user explicitly wants a full replacement,
        you know the complete desired chunk set, and you pass
        `confirm_full_replacement=True`.

        Args:
            source_id: The source ID.
            document_id: The document ID.
            chunks: List of chunk objects. Each chunk should have:
                - content (str): The text content.
                - metadata (dict, optional): Arbitrary metadata.
            confirm_full_replacement: Explicit acknowledgement that this is a
                risky full replacement operation, not a routine partial edit.
        """
        if not confirm_full_replacement:
            raise ValueError(
                "update_document_chunks is blocked by default because current backend sync is source-scoped. "
                "Retry only if the user explicitly wants a full replacement and pass confirm_full_replacement=True."
            )
        jwt, user_id = _get_auth()
        org = await require_role(user_id, "developer", "admin", "super_admin")
        return await api.put(
            f"/knowledge/organizations/{org['org_id']}/sources/{source_id}/documents/{document_id}",
            jwt,
            json=chunks,
        )
