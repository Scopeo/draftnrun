from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from ingestion_script import ingest_db_source
from ingestion_script.utils import SYNC_ID_COLUMN_NAME, UNIFIED_TABLE_DEFINITION


@pytest.mark.asyncio
async def test_upload_db_source_closes_sql_service_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_sql_local_service = MagicMock()
    fake_sql_local_service.close = AsyncMock()
    mock_sql_cls = MagicMock(return_value=fake_sql_local_service)
    monkeypatch.setattr(ingest_db_source, "SQLLocalService", mock_sql_cls)
    monkeypatch.setattr(ingest_db_source, "_validate_source_columns", lambda *args, **kwargs: {"id": "VARCHAR"})
    mock_get_ids = MagicMock(return_value={"source_table_1": None})
    monkeypatch.setattr(ingest_db_source, "get_db_source_ids", mock_get_ids)
    sync_chunks_to_qdrant_mock = AsyncMock()
    monkeypatch.setattr(ingest_db_source, "sync_chunks_to_qdrant", sync_chunks_to_qdrant_mock)

    db_service = MagicMock()
    qdrant_service = MagicMock()
    qdrant_service._build_combined_filter.return_value = None

    await ingest_db_source.upload_db_source(
        db_service=db_service,
        qdrant_service=qdrant_service,
        db_definition=UNIFIED_TABLE_DEFINITION,
        storage_schema_name="storage_schema",
        storage_table_name="storage_table",
        qdrant_collection_name="qdrant_collection",
        source_id=uuid4(),
        source_db_url="postgresql://example",
        source_table_name="source_table",
        id_column_name="id",
        text_column_names=["content"],
    )

    mock_sql_cls.assert_called_once_with(engine_url="postgresql://example")
    instance = mock_sql_cls.return_value
    mock_get_ids.assert_called_once()
    assert mock_get_ids.call_args.kwargs["sql_local_service"] is instance
    fetch_rows_fn = db_service.update_table.call_args.kwargs["fetch_rows_fn"]
    assert fetch_rows_fn.keywords["sql_local_service"] is instance
    instance.close.assert_awaited_once()
    db_service.update_table.assert_called_once()
    sync_chunks_to_qdrant_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_upload_db_source_closes_sql_service_on_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_sql_local_service = MagicMock()
    fake_sql_local_service.close = AsyncMock()
    monkeypatch.setattr(ingest_db_source, "SQLLocalService", lambda engine_url: fake_sql_local_service)
    monkeypatch.setattr(ingest_db_source, "_validate_source_columns", lambda *args, **kwargs: {"id": "VARCHAR"})
    monkeypatch.setattr(ingest_db_source, "get_db_source_ids", lambda *args, **kwargs: {})

    db_service = MagicMock()
    qdrant_service = MagicMock()
    qdrant_service._build_combined_filter.return_value = None

    with pytest.raises(ValueError, match="empty"):
        await ingest_db_source.upload_db_source(
            db_service=db_service,
            qdrant_service=qdrant_service,
            db_definition=UNIFIED_TABLE_DEFINITION,
            storage_schema_name="storage_schema",
            storage_table_name="storage_table",
            qdrant_collection_name="qdrant_collection",
            source_id=uuid4(),
            source_db_url="postgresql://example",
            source_table_name="source_table",
            id_column_name="id",
            text_column_names=["content"],
        )

    fake_sql_local_service.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_upload_db_source_uses_sync_id_as_id_column(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_sql_local_service = MagicMock()
    fake_sql_local_service.close = AsyncMock()
    monkeypatch.setattr(ingest_db_source, "SQLLocalService", MagicMock(return_value=fake_sql_local_service))
    monkeypatch.setattr(ingest_db_source, "_validate_source_columns", lambda *args, **kwargs: {"id": "VARCHAR"})
    monkeypatch.setattr(ingest_db_source, "get_db_source_ids", MagicMock(return_value={"row_1": None}))
    monkeypatch.setattr(ingest_db_source, "sync_chunks_to_qdrant", AsyncMock())

    db_service = MagicMock()
    qdrant_service = MagicMock()
    qdrant_service._build_combined_filter.return_value = None

    await ingest_db_source.upload_db_source(
        db_service=db_service,
        qdrant_service=qdrant_service,
        db_definition=UNIFIED_TABLE_DEFINITION,
        storage_schema_name="storage_schema",
        storage_table_name="storage_table",
        qdrant_collection_name="qdrant_collection",
        source_id=uuid4(),
        source_db_url="postgresql://example",
        source_table_name="source_table",
        id_column_name="id",
        text_column_names=["content"],
    )

    call_kwargs = db_service.update_table.call_args.kwargs
    assert call_kwargs["id_column_name"] == SYNC_ID_COLUMN_NAME


def test_fetch_db_source_chunks_sets_sync_id() -> None:
    fake_sql = MagicMock()
    fake_sql.get_table_rows.return_value = [
        {"id": 42, "content": "hello world"},
        {"id": 99, "content": "foo bar"},
    ]

    with patch("ingestion_script.ingest_db_source.SentenceSplitter") as mock_splitter_cls:
        mock_splitter_cls.return_value.split_text.side_effect = lambda txt: [txt]

        chunks = ingest_db_source.fetch_db_source_chunks(
            sync_ids={"42", "99"},
            sql_local_service=fake_sql,
            table_name="source_table",
            id_column_name="id",
            text_column_names=["content"],
        )

    assert len(chunks) == 2
    assert chunks[0][SYNC_ID_COLUMN_NAME] == "42"
    assert chunks[1][SYNC_ID_COLUMN_NAME] == "99"
    for chunk in chunks:
        assert SYNC_ID_COLUMN_NAME in chunk
