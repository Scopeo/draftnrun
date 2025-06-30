from typing import List
from pathlib import Path
from io import BytesIO

from data_ingestion.document.folder_management.folder_management import FileDocument, FileDocumentType, FolderManager
from data_ingestion.utils import get_last_modification_time_from_local_file


class DevLocalFolderManager(FolderManager):
    def __init__(self, path: str) -> None:
        super().__init__(path)

    def _get_file_info(self, file_path: str) -> FileDocument:
        file = Path(file_path)
        folder_path = file.parent
        return FileDocument(
            id=str(file_path),
            last_edited_ts=get_last_modification_time_from_local_file(file_path),
            type=FileDocumentType(file.suffix.lower()),
            file_name=file.name,
            folder_name=str(folder_path),
            metadata={"source_url": str(file)},
        )

    def _is_file(self, path: str) -> bool:
        return Path(path).is_file()

    def _has_valid_extension(self, path: str) -> bool:
        return Path(path).suffix in self.doc_possible_extensions

    def _get_file_id(self, path: str) -> str:
        return path

    def _walk_through_folder(self, path: str) -> List[str]:
        return [str(f) for f in Path(path).rglob("*") if f.is_file() and self._has_valid_extension(f)]

    def get_file_content(self, file_path: str) -> bytes:
        return BytesIO(Path(file_path).read_bytes()).getvalue()
