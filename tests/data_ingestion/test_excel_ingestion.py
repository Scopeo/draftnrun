from data_ingestion.document.excel_ingestion import ingest_excel_file
from data_ingestion.document.folder_management.folder_management import FileDocument, FileDocumentType

FILE_PATH = "tests/resources/documents/test_sample.xlsx"
EXPECTED_CONTENT = (
    "|   ids | test    |\n"
    "|------:|:--------|\n"
    "|     1 | test_1  |\n"
    "|     2 | test_2  |\n"
    "|     3 | test_3  |\n"
    "|     4 | test_4  |\n"
    "|     5 | test_5  |\n"
    "|     6 | test_6  |\n"
    "|     7 | test_7  |\n"
    "|     8 | test_8  |\n"
    "|     9 | test_9  |\n"
    "|    10 | test_10 |"
)


def get_file_content_func(file_id: str) -> bytes:
    with open(file_id, "rb") as f:
        return f.read()


def test_ingest_excel_file():
    document = FileDocument(
        id=FILE_PATH,
        type=FileDocumentType.EXCEL,
        file_name="test_excel.xlsx",
        folder_name="test_folder",
        last_edited_ts="2025-07-10T00:00:00Z",
        metadata={},
    )
    result = ingest_excel_file(document, get_file_content_func=get_file_content_func)
    print(result[0].content)
    assert len(result) == 1
    assert result[0].content == EXPECTED_CONTENT
    assert result[0].file_id == FILE_PATH
    assert result[0].chunk_id == f"{FILE_PATH}_test_0"
    assert result[0].document_title == "test_excel.xlsx"
    assert result[0].last_edited_ts == "2025-07-10T00:00:00Z"
    assert result[0].metadata == {}
    print(result)
