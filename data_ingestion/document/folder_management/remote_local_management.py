import base64
from io import BytesIO
from pathlib import Path
from typing import List

from data_ingestion.document.folder_management.folder_management import FileDocument, FileDocumentType, FolderManager


class RemoteFolderManager(FolderManager):
    def __init__(self, folder_payload: list[dict]) -> None:
        super().__init__("dummy_path")
        self._files = {
            f["path"]: {
                "name": f["name"],
                "last_edited_ts": f.get("last_edited_ts", None),
                "content": base64.b64decode(f["content"]),
                "metadata": f.get("metadata", {}),
            }
            for f in folder_payload
        }

    def _get_file_info(self, file_path: str) -> FileDocument:
        file_data = self._files[file_path]
        return FileDocument(
            id=file_path,
            last_edited_ts=file_data["last_edited_ts"],
            type=FileDocumentType(Path(file_path).suffix.lower()),
            file_name=file_data["name"],
            folder_name=str(Path(file_path).parent),
            metadata=file_data["metadata"],
        )

    def _is_file(self, path: str) -> bool:
        return path in self._files

    def _has_valid_extension(self, path: str) -> bool:
        extension = Path(path).suffix
        return extension in self.doc_possible_extensions

    def _get_file_id(self, path: str) -> str:
        return path

    def _walk_through_folder(self, path: str) -> List[str]:
        return [p for p in self._files if self._has_valid_extension(p)]

    def get_file_content(self, file_path: str) -> bytes:
        return BytesIO(self._files[file_path]["content"]).getvalue()
