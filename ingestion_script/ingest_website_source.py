import asyncio
import logging
from functools import partial
from typing import Optional
from uuid import UUID
import hashlib

from ada_backend.database import models as db
from ada_backend.schemas.ingestion_task_schema import SourceAttributes
from data_ingestion.document.document_chunking import (
    document_chunking_mapping,
    get_chunks_dataframe_from_doc,
)
from data_ingestion.document.folder_management.folder_management import WebsiteDocument
from firecrawl import AsyncFirecrawl
from engine.qdrant_service import QdrantService
from engine.storage_service.db_service import DBService
from ingestion_script.ingest_folder_source import (
    FILE_TABLE_DEFINITION,
    ID_COLUMN_NAME,
    QDRANT_SCHEMA,
    TIMESTAMP_COLUMN_NAME,
    load_llms_services,
    sync_chunks_to_qdrant,
)
from ingestion_script.utils import upload_source
from settings import settings

LOGGER = logging.getLogger(__name__)


async def scrape_website(
    url: str,
    follow_links: bool = False,
    max_depth: int = 1,
    selectors: Optional[dict[str, str]] = None,
    visited: Optional[set] = None,
    current_depth: int = 0,
    timeout: int = 30,
    limit: Optional[int] = None,
) -> list[dict]:
    """
    Scrape a website using Firecrawl API.

    Args:
        url: Starting URL
        follow_links: Whether to follow links (maps to crawl_entire_domain)
        max_depth: Maximum depth for link following (maps to maxDiscoveryDepth)
        selectors: CSS selectors for content extraction (not used with Firecrawl, kept for compatibility)
        visited: Set of already visited URLs (not used with Firecrawl, kept for compatibility)
        current_depth: Current depth in the crawl (not used with Firecrawl, kept for compatibility)
        timeout: Request timeout in seconds (not used with Firecrawl, kept for compatibility)
        limit: Maximum number of pages to crawl

    Returns:
        List of scraped page data with 'url', 'title', 'content', 'html'
    """
    LOGGER.info(f"Starting Firecrawl scrape for URL: {url} (follow_links={follow_links}, max_depth={max_depth})")

    try:
        # Initialize Firecrawl client with API key from settings
        if not settings.FIRECRAWL_API_KEY:
            raise ValueError("Firecrawl API key is required. Set FIRECRAWL_API_KEY in settings.")

        firecrawl = AsyncFirecrawl(api_key=settings.FIRECRAWL_API_KEY)

        # Build crawl options
        crawl_options = {
            "limit": limit,
            "scrapeOptions": {
                "formats": ["markdown", "html"],
                "onlyMainContent": True,
            },
        }

        # Map follow_links to crawl_entire_domain
        if follow_links:
            crawl_options["crawlEntireDomain"] = True
            if max_depth > 0:
                crawl_options["maxDepth"] = max_depth

        # Start the crawl - the SDK handles polling automatically
        LOGGER.info(f"Starting Firecrawl crawl with options: {crawl_options}")
        crawl_result = await firecrawl.crawl(url, **crawl_options)

        # The SDK's crawl method returns the results directly after polling
        if not crawl_result or not crawl_result.get("data"):
            raise ValueError(f"Failed to crawl: {crawl_result}")

        pages = crawl_result.get("data", [])
        LOGGER.info(f"Firecrawl crawl completed. Found {len(pages)} pages")

        # Convert Firecrawl format to our expected format
        scraped_pages = []
        for page in pages:
            page_url = page.get("url", url)
            page_title = page.get("metadata", {}).get("title") or page.get("title", "") or page_url
            markdown_content = page.get("markdown", "") or page.get("content", "")
            html_content = page.get("html", "")

            if not markdown_content and not html_content:
                LOGGER.warning(f"No content found for page: {page_url}")
                continue

            scraped_pages.append(
                {
                    "url": page_url,
                    "title": page_title,
                    "content": markdown_content,
                    "html": html_content,
                }
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
    urls_to_scrape: list[str],
    follow_links: bool = False,
    max_depth: int = 1,
    selectors: Optional[dict[str, str]] = None,
    chunk_size: int = 1024,
    chunk_overlap: int = 0,
    update_existing: bool = False,
) -> None:
    """
    Upload website content to database and Qdrant.
    This function is called by upload_source utility.
    """
    LOGGER.info(f"Starting to scrape {len(urls_to_scrape)} URL(s)")
    all_scraped_data = []

    for url_to_scrape in urls_to_scrape:
        scraped_pages = await scrape_website(
            url=url_to_scrape, follow_links=follow_links, max_depth=max_depth, selectors=selectors
        )
        all_scraped_data.extend(scraped_pages)

    if not all_scraped_data:
        LOGGER.warning("No content scraped from URLs")
        return

    LOGGER.info(f"Scraped {len(all_scraped_data)} pages")

    if settings.USE_LLM_FOR_PDF_PARSING:
        try:
            vision_completion_service, fallback_vision_llm_service = load_llms_services()
        except ValueError as e:
            LOGGER.warning(f"Failed to load LLM services: {str(e)}")
            vision_completion_service = None
            fallback_vision_llm_service = None
    else:
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

    for page_data in all_scraped_data:
        if not page_data.get("content") or not page_data["content"].strip():
            LOGGER.warning(f"Skipping page {page_data['url']} - no content extracted")
            continue

        file_id = hashlib.md5(page_data["url"].encode()).hexdigest()
        content_storage[file_id] = page_data["content"].encode("utf-8")

        document = WebsiteDocument(
            id=file_id,
            file_name=page_data["title"],
            folder_name="",
            metadata={
                "url": page_data["url"],
                "content": page_data["content"],
                "title": page_data["title"],
                "source_url": page_data["url"],
            },
        )

        chunks_df = await get_chunks_dataframe_from_doc(
            document,
            document_chunk_mapping,
            llm_service=fallback_vision_llm_service,
            add_doc_description_to_chunks=False,
            documents_summary_func=None,
            add_summary_in_chunks_func=None,
            default_chunk_size=chunk_size,
        )

        if chunks_df.empty:
            LOGGER.warning(f"No chunks created for {page_data['url']} - skipping")
            continue

        if "url" not in chunks_df.columns:
            chunks_df["url"] = page_data["url"]
        else:
            chunks_df["url"] = page_data["url"]

        LOGGER.info(f"Syncing {len(chunks_df)} chunks to db table {storage_table_name} for {page_data['url']}")
        db_service.update_table(
            new_df=chunks_df,
            table_name=storage_table_name,
            table_definition=FILE_TABLE_DEFINITION,
            id_column_name=ID_COLUMN_NAME,
            timestamp_column_name=TIMESTAMP_COLUMN_NAME,
            append_mode=update_existing,
            schema_name=storage_schema_name,
        )

        await sync_chunks_to_qdrant(
            storage_schema_name, storage_table_name, qdrant_collection_name, db_service, qdrant_service
        )


async def ingest_website_source(
    url: Optional[str] = None,
    urls: Optional[list[str]] = None,
    organization_id: str = None,
    source_name: str = None,
    task_id: UUID = None,
    follow_links: bool = False,
    max_depth: int = 1,
    selectors: Optional[dict[str, str]] = None,
    chunk_size: Optional[int] = 1024,
    chunk_overlap: Optional[int] = 0,
    source_attributes: Optional[SourceAttributes] = None,
    source_id: Optional[UUID] = None,
) -> None:
    """
    Ingest content from one or more websites.
    """
    LOGGER.info(
        f"[INGESTION_SOURCE] Starting WEBSITE ingestion - Source: '{source_name}', "
        f"URL(s): {url or urls}, Organization: {organization_id}"
    )

    urls_to_scrape = []
    if urls:
        urls_to_scrape = urls
    elif url:
        urls_to_scrape = [url]
    else:
        raise ValueError("Either 'url' or 'urls' must be provided")

    qdrant_schema = QDRANT_SCHEMA
    source_type = db.SourceType.WEBSITE
    update_existing = source_attributes.update_existing if source_attributes else False

    LOGGER.info("Start ingestion data from the website source...")
    await upload_source(
        source_name,
        organization_id,
        task_id,
        source_type,
        qdrant_schema,
        update_existing=update_existing,
        ingestion_function=partial(
            upload_website_source,
            urls_to_scrape=urls_to_scrape,
            follow_links=follow_links,
            max_depth=max_depth,
            selectors=selectors,
            chunk_size=chunk_size or 1024,
            chunk_overlap=chunk_overlap or 0,
        ),
        attributes=source_attributes,
        source_id=source_id,
    )
