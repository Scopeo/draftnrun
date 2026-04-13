from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from data_ingestion.document.excel_ingestion import create_chunks_from_excel_file_with_llamaparse
from data_ingestion.document.folder_management.folder_management import FileDocument, FileDocumentType, FolderManager
from data_ingestion.document.folder_management.s3_folder_management import S3FolderManager
from data_ingestion.document.mistral_ocr_ingestion import get_chunks_from_document_with_mistral_ocr
from data_ingestion.document.pdf_ingestion import create_chunks_from_pdf_document


@pytest.fixture
def pdf_document():
    return FileDocument(
        id="org/test.pdf",
        last_edited_ts="2025-01-01T00:00:00Z",
        type=FileDocumentType.PDF,
        file_name="test.pdf",
        folder_name="org",
    )


@pytest.fixture
def excel_document():
    return FileDocument(
        id="org/test.xlsx",
        last_edited_ts="2025-01-01T00:00:00Z",
        type=FileDocumentType.EXCEL,
        file_name="test.xlsx",
        folder_name="org",
    )


class TestFolderManagerPresignedUrl:
    def test_base_folder_manager_returns_none(self):
        class DummyFolderManager(FolderManager):
            def _get_file_info(self, file):
                pass

            def _is_file(self, path):
                return False

            def _has_valid_extension(self, path):
                return True

            def _get_file_id(self, path):
                return path

            def _walk_through_folder(self, path):
                return []

            def get_file_content(self, path):
                return b""

        manager = DummyFolderManager("dummy")
        assert manager.get_file_presigned_url("any_path") is None


class TestS3FolderManagerPresignedUrl:
    @patch("data_ingestion.document.folder_management.s3_folder_management.get_s3_boto3_client")
    def test_returns_none_when_custom_endpoint(self, mock_get_client):
        mock_get_client.return_value = MagicMock()
        manager = S3FolderManager(
            folder_payload=[{"path": "f1", "name": "f1.pdf", "s3_path": "org/f1.pdf"}],
            bucket_name="test-bucket",
            s3_url_endpoint="http://localhost:8333",
            s3_access_key_id="key",
            s3_secret_access_key="secret",
            s3_region_name="us-east-1",
        )
        assert manager.get_file_presigned_url("f1") is None

    @patch("data_ingestion.document.folder_management.s3_folder_management.get_s3_boto3_client")
    def test_returns_presigned_url_when_aws(self, mock_get_client):
        mock_s3 = MagicMock()
        mock_s3.generate_presigned_url.return_value = "https://bucket.s3.amazonaws.com/org/f1.pdf?X-Amz-Signature=abc"
        mock_get_client.return_value = mock_s3

        manager = S3FolderManager(
            folder_payload=[{"path": "f1", "name": "f1.pdf", "s3_path": "org/f1.pdf"}],
            bucket_name="test-bucket",
            s3_url_endpoint="",
            s3_access_key_id="key",
            s3_secret_access_key="secret",
            s3_region_name="us-east-1",
        )
        url = manager.get_file_presigned_url("f1")
        assert url is not None
        assert "X-Amz-Signature" in url
        mock_s3.generate_presigned_url.assert_called_once_with(
            ClientMethod="get_object",
            Params={"Bucket": "test-bucket", "Key": "org/f1.pdf"},
            ExpiresIn=3600,
        )

    @patch("data_ingestion.document.folder_management.s3_folder_management.get_s3_boto3_client")
    def test_returns_none_when_no_s3_path(self, mock_get_client):
        mock_get_client.return_value = MagicMock()
        manager = S3FolderManager(
            folder_payload=[{"path": "f1", "name": "f1.pdf", "s3_path": None}],
            bucket_name="test-bucket",
            s3_url_endpoint="",
            s3_access_key_id="key",
            s3_secret_access_key="secret",
            s3_region_name="us-east-1",
        )
        assert manager.get_file_presigned_url("f1") is None


class TestMistralOcrPresignedUrl:
    @pytest.mark.asyncio
    async def test_uses_presigned_url_when_available(self, pdf_document):
        mock_get_content = MagicMock(return_value=b"pdf bytes")
        mock_get_url = MagicMock(return_value="https://s3.amazonaws.com/bucket/file.pdf?sig=abc")

        ocr_json = '{"pages": [{"markdown": "# Hello World"}]}'
        with patch("data_ingestion.document.mistral_ocr_ingestion.OCRService") as MockOCR:
            mock_ocr_instance = MagicMock()
            mock_ocr_instance.get_ocr_text_async = AsyncMock(return_value=ocr_json)
            MockOCR.return_value = mock_ocr_instance

            result = await get_chunks_from_document_with_mistral_ocr(
                document=pdf_document,
                get_file_content=mock_get_content,
                mistral_ocr_api_key="test-key",
                get_file_url=mock_get_url,
            )

        mock_get_url.assert_called_once_with("org/test.pdf")
        mock_get_content.assert_not_called()
        assert len(result) >= 1

    @pytest.mark.asyncio
    async def test_falls_back_to_base64_when_no_url(self, pdf_document):
        mock_get_content = MagicMock(return_value=b"pdf bytes")

        ocr_json = '{"pages": [{"markdown": "# Hello World"}]}'
        with patch("data_ingestion.document.mistral_ocr_ingestion.OCRService") as MockOCR:
            mock_ocr_instance = MagicMock()
            mock_ocr_instance.get_ocr_text_async = AsyncMock(return_value=ocr_json)
            MockOCR.return_value = mock_ocr_instance

            result = await get_chunks_from_document_with_mistral_ocr(
                document=pdf_document,
                get_file_content=mock_get_content,
                mistral_ocr_api_key="test-key",
                get_file_url=None,
            )

        mock_get_content.assert_called_once_with("org/test.pdf")
        assert len(result) >= 1

    @pytest.mark.asyncio
    async def test_falls_back_to_base64_when_url_returns_none(self, pdf_document):
        mock_get_content = MagicMock(return_value=b"pdf bytes")
        mock_get_url = MagicMock(return_value=None)

        ocr_json = '{"pages": [{"markdown": "# Hello World"}]}'
        with patch("data_ingestion.document.mistral_ocr_ingestion.OCRService") as MockOCR:
            mock_ocr_instance = MagicMock()
            mock_ocr_instance.get_ocr_text_async = AsyncMock(return_value=ocr_json)
            MockOCR.return_value = mock_ocr_instance

            result = await get_chunks_from_document_with_mistral_ocr(
                document=pdf_document,
                get_file_content=mock_get_content,
                mistral_ocr_api_key="test-key",
                get_file_url=mock_get_url,
            )

        mock_get_content.assert_called_once_with("org/test.pdf")
        assert len(result) >= 1


class TestPdfIngestionPresignedUrl:
    @pytest.mark.asyncio
    async def test_uses_presigned_url_skips_download(self, pdf_document):
        mock_get_content = MagicMock(return_value=b"pdf bytes")
        mock_get_url = MagicMock(return_value="https://s3.amazonaws.com/bucket/test.pdf?sig=abc")
        mock_parser = AsyncMock(return_value="# Parsed content")

        result = await create_chunks_from_pdf_document(
            document=pdf_document,
            get_file_content=mock_get_content,
            pdf_parser=mock_parser,
            get_file_url=mock_get_url,
        )

        mock_get_url.assert_called_once_with("org/test.pdf")
        mock_get_content.assert_not_called()
        mock_parser.assert_called_once()
        call_kwargs = mock_parser.call_args
        assert call_kwargs.kwargs["file_url"] == "https://s3.amazonaws.com/bucket/test.pdf?sig=abc"
        assert len(result) >= 1

    @pytest.mark.asyncio
    async def test_falls_back_to_temp_file_when_no_url(self, pdf_document):
        mock_get_content = MagicMock(return_value=b"%PDF-1.4 fake content")
        mock_parser = AsyncMock(return_value="# Parsed content")

        with patch("data_ingestion.document.pdf_ingestion.content_as_temporary_file_path") as mock_ctx:
            mock_ctx.return_value.__enter__ = MagicMock(return_value="/tmp/test.pdf")
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

            result = await create_chunks_from_pdf_document(
                document=pdf_document,
                get_file_content=mock_get_content,
                pdf_parser=mock_parser,
                get_file_url=None,
            )

        mock_get_content.assert_called_once_with("org/test.pdf")
        assert len(result) >= 1


class TestExcelIngestionPresignedUrl:
    @pytest.mark.asyncio
    async def test_uses_presigned_url_skips_download(self, excel_document):
        mock_get_content = MagicMock(return_value=b"excel bytes")
        mock_get_url = MagicMock(return_value="https://s3.amazonaws.com/bucket/test.xlsx?sig=abc")

        mock_path = "data_ingestion.document.excel_ingestion._parse_document_with_llamaparse"
        with patch(mock_path, new_callable=AsyncMock) as mock_parse:
            mock_parse.return_value = [("| col1 | col2 |\n|---|---|\n| a | b |", 1)]

            result = await create_chunks_from_excel_file_with_llamaparse(
                document=excel_document,
                get_file_content_func=mock_get_content,
                llamaparse_api_key="test-key",
                get_file_url=mock_get_url,
            )

        mock_get_url.assert_called_once_with("org/test.xlsx")
        mock_get_content.assert_not_called()
        mock_parse.assert_called_once_with(
            "presigned_url_input",
            "test-key",
            split_by_page=True,
            file_url="https://s3.amazonaws.com/bucket/test.xlsx?sig=abc",
        )
        assert len(result) >= 1

    @pytest.mark.asyncio
    async def test_falls_back_to_temp_file_when_no_url(self, excel_document):
        mock_get_content = MagicMock(return_value=b"excel bytes")

        mock_path = "data_ingestion.document.excel_ingestion._parse_document_with_llamaparse"
        with patch(mock_path, new_callable=AsyncMock) as mock_parse:
            mock_parse.return_value = [("| col1 | col2 |\n|---|---|\n| a | b |", 1)]

            with patch("data_ingestion.document.excel_ingestion.content_as_temporary_file_path") as mock_ctx:
                mock_ctx.return_value.__enter__ = MagicMock(return_value="/tmp/test.xlsx")
                mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

                result = await create_chunks_from_excel_file_with_llamaparse(
                    document=excel_document,
                    get_file_content_func=mock_get_content,
                    llamaparse_api_key="test-key",
                    get_file_url=None,
                )

        mock_get_content.assert_called_once_with("org/test.xlsx")
        assert len(result) >= 1
