from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pandas as pd
import pytest

from ingestion_script.ingest_website_source import ScrapedPage, scrape_website, upload_website_source
from ingestion_script.utils import UNIFIED_TABLE_DEFINITION
from settings import settings


@pytest.mark.asyncio
async def test_scrape_website_builds_expected_firecrawl_options(monkeypatch):
    monkeypatch.setattr(settings, "FIRECRAWL_API_KEY", "test-key", raising=False)

    captured_call = {}

    class FakePage:
        def __init__(self):
            self.metadata = SimpleNamespace(url="https://example.com/page", title="Example page")
            self.markdown = "# Heading\nSome content"

    class FakeResult:
        def __init__(self, data):
            self.data = data

    class FakeFirecrawl:
        def __init__(self, api_key):
            self.api_key = api_key

        async def crawl(self, url, **kwargs):
            captured_call["url"] = url
            captured_call["kwargs"] = kwargs
            return FakeResult([FakePage()])

    monkeypatch.setattr("ingestion_script.ingest_website_source.AsyncFirecrawl", FakeFirecrawl)

    pages = await scrape_website(
        url="https://example.com",
        follow_links=True,
        max_depth=2,
        limit=5,
        include_paths=["/docs"],
        exclude_paths=["/admin"],
        include_tags=["p"],
        exclude_tags=["img"],
    )

    assert len(pages) == 1
    page = pages[0]
    assert isinstance(page, ScrapedPage)
    assert page.url == "https://example.com/page"
    assert page.title == "Example page"
    assert page.content == "# Heading\nSome content"
    assert captured_call["url"] == "https://example.com"
    options = captured_call["kwargs"]
    assert options["limit"] == 5
    assert options["includePaths"] == ["/docs"]
    assert options["excludePaths"] == ["/admin"]
    assert options["crawlEntireDomain"] is True
    assert options["maxDepth"] == 2
    assert options["scrapeOptions"] == {
        "formats": ["markdown"],
        "onlyMainContent": True,
        "includeTags": ["p"],
        "excludeTags": ["img"],
    }


@pytest.mark.asyncio
async def test_upload_website_source_syncs_scraped_pages(monkeypatch):
    scraped_pages = [
        ScrapedPage(
            url="https://example.com/page",
            title="Example page",
            content="# Heading\nSome content",
        )
    ]
    scrape_mock = AsyncMock(return_value=scraped_pages)
    monkeypatch.setattr("ingestion_script.ingest_website_source.scrape_website", scrape_mock)

    chunk_df = pd.DataFrame({
        "chunk_id": ["chunk-1"],
        "file_id": ["file-1"],
        "content": ["chunk content"],
        "url": ["https://example.com/page"],
        "document_title": ["Example page"],
        "last_edited_ts": ["2025-01-01T00:00:00Z"],
        "metadata": ["{}"],
        "order": [0],
    })
    chunks_mock = AsyncMock(return_value=chunk_df)
    monkeypatch.setattr(
        "ingestion_script.ingest_website_source.get_chunks_dataframe_from_doc",
        chunks_mock,
    )

    mapping_sentinel = object()
    mapping_mock = MagicMock(return_value=mapping_sentinel)
    monkeypatch.setattr(
        "ingestion_script.ingest_website_source.document_chunking_mapping",
        mapping_mock,
    )

    sync_mock = AsyncMock()
    monkeypatch.setattr(
        "ingestion_script.ingest_website_source.sync_chunks_to_qdrant",
        sync_mock,
    )

    db_service = MagicMock()
    qdrant_service = MagicMock()
    test_source_id = UUID("12345678-1234-5678-1234-567812345678")

    await upload_website_source(
        db_service=db_service,
        qdrant_service=qdrant_service,
        storage_schema_name="web_schema",
        storage_table_name="web_table",
        qdrant_collection_name="web_collection",
        source_id=test_source_id,
        url="https://example.com",
        follow_links=True,
        max_depth=3,
        limit=42,
        include_paths=["/docs"],
        exclude_paths=["/admin"],
        include_tags=["p"],
        exclude_tags=["img"],
        chunk_size=256,
        chunk_overlap=16,
        update_existing=False,
    )

    scrape_mock.assert_awaited_once_with(
        url="https://example.com",
        follow_links=True,
        max_depth=3,
        limit=42,
        include_paths=["/docs"],
        exclude_paths=["/admin"],
        include_tags=["p"],
        exclude_tags=["img"],
    )
    mapping_mock.assert_called_once()
    _, mapping_kwargs = mapping_mock.call_args
    assert mapping_kwargs["chunk_size"] == 256
    assert mapping_kwargs["overlapping_size"] == 16
    assert mapping_kwargs["use_llm_for_pdf"] is False

    document_arg = chunks_mock.await_args.args[0]
    assert document_arg.metadata["source_url"] == "https://example.com/page"
    assert document_arg.metadata["title"] == "Example page"

    assert chunks_mock.await_args.kwargs["document_chunk_mapping"] is mapping_sentinel
    db_service.create_schema.assert_called_once_with("web_schema")
    db_service.update_table.assert_called_once()
    update_kwargs = db_service.update_table.call_args.kwargs
    assert update_kwargs["table_name"] == "web_table"
    assert update_kwargs["schema_name"] == "web_schema"
    assert update_kwargs["table_definition"] is UNIFIED_TABLE_DEFINITION
    assert update_kwargs["append_mode"] is True

    sync_mock.assert_awaited_once_with(
        "web_schema",
        "web_table",
        "web_collection",
        db_service,
        qdrant_service,
        source_id=str(test_source_id),
    )
