from data_ingestion.document.folder_management.folder_management import FileDocumentType
from data_ingestion.document.folder_management.local_folder_management import LocalFolderManager


def test_list_folder_documents():
    path = "tests/resources/documents"
    folder_manager = LocalFolderManager(path)
    documents = folder_manager.list_all_files_info()
    assert documents is not None
    assert len(documents) == 3
    documents = sorted(documents, key=lambda x: x.id)
    assert documents[0].id == "tests/resources/documents/test_docx.docx"
    assert documents[0].type == FileDocumentType.DOCX
    assert documents[0].file_name == "test_docx.docx"
    assert documents[0].folder_name == "tests/resources/documents"
    assert documents[1].id == "tests/resources/documents/test_markdown.md"
    assert documents[1].type == FileDocumentType.MARKDOWN
    assert documents[1].file_name == "test_markdown.md"
    assert documents[1].folder_name == "tests/resources/documents"
    assert documents[2].id == "tests/resources/documents/test_pdf.pdf"
    assert documents[2].type == FileDocumentType.PDF
    assert documents[2].file_name == "test_pdf.pdf"
    assert documents[2].folder_name == "tests/resources/documents"
