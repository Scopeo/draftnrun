from data_ingestion.document.folder_management.folder_management import FileDocumentType
from data_ingestion.document.folder_management.dev_local_folder_management import DevLocalFolderManager


def test_list_folder_documents():
    path = "tests/resources/documents"
    folder_manager = DevLocalFolderManager(path)
    documents = folder_manager.list_all_files_info()
    assert documents is not None
    assert len(documents) == 4
    documents = sorted(documents, key=lambda x: x.id)
    print(documents)
    assert documents[0].id == "tests/resources/documents/sample.pdf"
    assert documents[0].type == FileDocumentType.PDF
    assert documents[0].file_name == "sample.pdf"
    assert documents[1].id == "tests/resources/documents/test_docx.docx"
    assert documents[1].type == FileDocumentType.DOCX
    assert documents[1].file_name == "test_docx.docx"
    assert documents[1].folder_name == "tests/resources/documents"
    assert documents[2].id == "tests/resources/documents/test_markdown.md"
    assert documents[2].type == FileDocumentType.MARKDOWN
    assert documents[2].file_name == "test_markdown.md"
    assert documents[2].folder_name == "tests/resources/documents"
    assert documents[3].id == "tests/resources/documents/test_pdf.pdf"
    assert documents[3].type == FileDocumentType.PDF
    assert documents[3].file_name == "test_pdf.pdf"
    assert documents[3].folder_name == "tests/resources/documents"
