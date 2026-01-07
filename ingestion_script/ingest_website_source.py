import hashlib
import logging
from functools import partial
from typing import Optional
from uuid import UUID

import pandas as pd
from firecrawl import AsyncFirecrawl
from pydantic import BaseModel

from ada_backend.database import models as db
from data_ingestion.document.document_chunking import (
    document_chunking_mapping,
    get_chunks_dataframe_from_doc,
)
from data_ingestion.document.folder_management.folder_management import WebsiteDocument
from engine.qdrant_service import QdrantService
from engine.storage_service.db_service import DBService
from ingestion_script.ingest_folder_source import (
    TIMESTAMP_COLUMN_NAME,
    UNIFIED_QDRANT_SCHEMA,
    UNIFIED_TABLE_DEFINITION,
    sync_chunks_to_qdrant,
)
from ingestion_script.utils import (
    CHUNK_ID_COLUMN_NAME,
    transform_chunks_df_for_unified_table,
    upload_source,
)
from settings import settings

LOGGER = logging.getLogger(__name__)


class ScrapedPage(BaseModel):
    url: str
    title: str
    content: str


async def scrape_website(
    url: str,
    follow_links: bool = False,
    max_depth: int = 1,
    limit: Optional[int] = 100,
    include_paths: Optional[list[str]] = None,
    exclude_paths: Optional[list[str]] = None,
    include_tags: Optional[list[str]] = None,
    exclude_tags: Optional[list[str]] = None,
) -> list[ScrapedPage]:
    """
    Scrape a website using Firecrawl API.

    Args:
        url: Starting URL to crawl
        follow_links: Whether to follow links (maps to crawlEntireDomain)
        max_depth: Maximum depth for link following (maps to maxDepth)
        limit: Maximum number of pages to crawl (default: 100).
               Recommended: 10-100 for small sites, 100-500 for medium sites, 500+ for large sites.
        include_paths: URL pathname regex patterns that include matching URLs
        exclude_paths: URL pathname regex patterns that exclude matching URLs
        include_tags: HTML tags to include in content extraction
        exclude_tags: HTML tags to exclude from content extraction

    Returns:
        List of scraped page data with 'url', 'title', 'content'
    """
    LOGGER.info(
        f"Starting Firecrawl scrape for URL: {url} (follow_links={follow_links}, max_depth={max_depth}, "
        f"limit={limit}, include_paths={include_paths}, exclude_paths={exclude_paths})"
    )

    try:
        if not settings.FIRECRAWL_API_KEY:
            raise ValueError("Firecrawl API key is required. Set FIRECRAWL_API_KEY in settings.")

        firecrawl = AsyncFirecrawl(api_key=settings.FIRECRAWL_API_KEY)

        scrape_options = {
            "formats": ["markdown"],
            "onlyMainContent": True,
        }

        if include_tags:
            scrape_options["includeTags"] = include_tags
        if exclude_tags:
            scrape_options["excludeTags"] = exclude_tags

        crawl_options = {
            "limit": limit,
            "scrapeOptions": scrape_options,
        }

        if include_paths:
            crawl_options["includePaths"] = include_paths
        if exclude_paths:
            crawl_options["excludePaths"] = exclude_paths

        if follow_links:
            crawl_options["crawlEntireDomain"] = True
            if max_depth > 0:
                crawl_options["maxDepth"] = max_depth

        LOGGER.info(f"Starting Firecrawl crawl with options: {crawl_options}")
        crawl_result = await firecrawl.crawl(url=url, **crawl_options)

        if not crawl_result or not crawl_result.data:
            raise ValueError(f"Failed to crawl: {crawl_result}")

        pages = crawl_result.data
        LOGGER.info(f"Firecrawl crawl completed. Found {len(pages)} pages")

        scraped_pages: list[ScrapedPage] = []
        for page in pages:
            page_url = (page.metadata.url if page.metadata else None) or url
            page_title = (page.metadata.title if page.metadata else None) or page_url
            markdown_content = page.markdown or ""

            if not markdown_content:
                LOGGER.warning(f"No content found for page: {page_url}")
                continue

            scraped_pages.append(
                ScrapedPage(
                    url=page_url,
                    title=page_title,
                    content=markdown_content,
                )
            )

        return scraped_pages

    except Exception as e:
        LOGGER.error(f"Error scraping website {url} with Firecrawl: {str(e)}")
        raise


async def upload_website_source(
    db_service: DBService,
    qdrant_service: QdrantService,
    storage_schema_name: str,
    storage_table_name: str,
    qdrant_collection_name: str,
    source_id: UUID,
    url: str,
    follow_links: bool = True,
    max_depth: int = 1,
    limit: Optional[int] = 100,
    include_paths: Optional[list[str]] = None,
    exclude_paths: Optional[list[str]] = None,
    include_tags: Optional[list[str]] = None,
    exclude_tags: Optional[list[str]] = None,
    chunk_size: int = 1024,
    chunk_overlap: int = 0,
    update_existing: bool = False,
) -> None:
    LOGGER.info(f"Starting to scrape URL: {url} using Firecrawl")

    scraped_pages = await scrape_website(
        url=url,
        follow_links=follow_links,
        max_depth=max_depth,
        limit=limit,
        include_paths=include_paths,
        exclude_paths=exclude_paths,
        include_tags=include_tags,
        exclude_tags=exclude_tags,
    )

    if not scraped_pages:
        LOGGER.warning("No content scraped from URLs")
        return

    LOGGER.info(f"Scraped {len(scraped_pages)} pages")

    # Firecrawl content is already Markdown, so no LLM/vision processing is required.
    vision_completion_service = None
    fallback_vision_llm_service = None

    content_storage = {}

    def get_file_content_func(file_id: str) -> bytes:
        return content_storage.get(file_id, b"")

    document_chunk_mapping = document_chunking_mapping(
        vision_ingestion_service=vision_completion_service,
        llm_service=fallback_vision_llm_service,
        get_file_content_func=get_file_content_func,
        chunk_size=chunk_size,
        overlapping_size=chunk_overlap,
        use_llm_for_pdf=False,
    )

    db_service.create_schema(storage_schema_name)

    page_chunks_dfs = []

    for page_data in scraped_pages:
        if not page_data.content or not page_data.content.strip():
            LOGGER.warning(f"Skipping page {page_data.url} - no content extracted")
            continue

        file_id = hashlib.md5(page_data.url.encode()).hexdigest()
        content_storage[file_id] = page_data.content.encode("utf-8")

        document = WebsiteDocument(
            id=file_id,
            file_name=page_data.title if page_data.title else page_data.url,
            folder_name=page_data.url,
            metadata={
                "title": page_data.title,
                "source_url": page_data.url,
            },
        )

        chunks_df = await get_chunks_dataframe_from_doc(
            document,
            document_chunk_mapping=document_chunk_mapping,
            add_doc_description_to_chunks=False,
            documents_summary_func=None,
            add_summary_in_chunks_func=None,
            default_chunk_size=chunk_size,
        )

        if chunks_df.empty:
            LOGGER.warning(f"No chunks created for {page_data.url} - skipping")
            continue

        chunks_df["url"] = page_data.url
        page_chunks_dfs.append(chunks_df)
        LOGGER.info(f"Created {len(chunks_df)} chunks for {page_data.url}")

    if not page_chunks_dfs:
        LOGGER.warning("No chunks created from any page - nothing to sync")
        return

    all_chunks_df = pd.concat(page_chunks_dfs, ignore_index=True)

    initial_count = len(all_chunks_df)
    all_chunks_df = all_chunks_df[all_chunks_df["content"].notna() & (all_chunks_df["content"].str.strip() != "")]
    filtered_count = initial_count - len(all_chunks_df)
    if filtered_count > 0:
        LOGGER.info(f"Filtered out {filtered_count} chunks with empty content")

    if all_chunks_df.empty:
        LOGGER.warning("No valid chunks remaining after filtering - nothing to sync")
        return

    LOGGER.info(f"Syncing {len(all_chunks_df)} total chunks to db table {storage_table_name}")

    all_chunks_df_for_db = transform_chunks_df_for_unified_table(all_chunks_df, source_id)

    db_service.update_table(
        new_df=all_chunks_df_for_db,
        table_name=storage_table_name,
        table_definition=UNIFIED_TABLE_DEFINITION,
        id_column_name=CHUNK_ID_COLUMN_NAME,
        timestamp_column_name=TIMESTAMP_COLUMN_NAME,
        append_mode=True,
        schema_name=storage_schema_name,
        source_id=str(source_id),  # Pass source_id to filter existing IDs by source
    )

    await sync_chunks_to_qdrant(
        storage_schema_name,
        storage_table_name,
        qdrant_collection_name,
        db_service,
        qdrant_service,
        source_id=str(source_id),
    )


async def ingest_website_source(
    url: str,
    organization_id: str = None,
    source_name: str = None,
    task_id: UUID = None,
    follow_links: bool = True,
    max_depth: int = 1,
    limit: Optional[int] = 100,
    include_paths: Optional[list[str]] = None,
    exclude_paths: Optional[list[str]] = None,
    include_tags: Optional[list[str]] = None,
    exclude_tags: Optional[list[str]] = None,
    chunk_size: Optional[int] = 1024,
    chunk_overlap: Optional[int] = 0,
    source_id: Optional[UUID] = None,
) -> None:
    LOGGER.info(
        f"[INGESTION_SOURCE] Starting WEBSITE ingestion with Firecrawl - Source: '{source_name}', "
        f"URL: {url}, Organization: {organization_id}"
    )

    source_type = db.SourceType.WEBSITE

    LOGGER.info("Starting Firecrawl website ingestion...")
    await upload_source(
        source_name,
        organization_id,
        task_id,
        source_type,
        UNIFIED_QDRANT_SCHEMA,
        update_existing=False,
        ingestion_function=partial(
            upload_website_source,
            url=url,
            follow_links=follow_links,
            max_depth=max_depth,
            limit=limit,
            include_paths=include_paths,
            exclude_paths=exclude_paths,
            include_tags=include_tags,
            exclude_tags=exclude_tags,
            chunk_size=chunk_size or 1024,
            chunk_overlap=chunk_overlap or 0,
        ),
        attributes=None,
        source_id=source_id,
    )
