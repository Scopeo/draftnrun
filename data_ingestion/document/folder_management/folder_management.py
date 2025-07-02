from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, List, Optional
import logging

from pydantic import BaseModel, Field

from data_ingestion.utils import Chunk

LOGGER = logging.getLogger(__name__)


class FileDocumentType(Enum):
    PDF = ".pdf"
    DOCX = ".docx"
    MARKDOWN = ".md"
    EXCEL = ".xlsx"
    CSV = ".csv"

    @classmethod
    def from_mime_type(cls, mime_type: str):
        """Maps MIME type to the corresponding FileDocumentType."""
        mime_map = {
            "application/pdf": cls.PDF,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document": cls.DOCX,
            "text/markdown": cls.MARKDOWN,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": cls.EXCEL,
            "text/csv": cls.CSV,
        }
        return mime_map.get(mime_type, None)


class FileChunk(Chunk):
    document_title: str
    bounding_boxes: list[dict]
    url: Optional[str] = None


class FileDocument(BaseModel):
    id: str
    last_edited_ts: str
    type: FileDocumentType
    file_name: str
    folder_name: str
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def url(self) -> str | None:
        return self.metadata.get("supabase_url") or self.metadata.get("source_url", None)


class FolderManager(ABC):
    doc_possible_extensions = [doctype.value for doctype in FileDocumentType]

    def __init__(self, path: str) -> None:
        self.path = path
        pass

    @abstractmethod
    def _get_file_info(self, file) -> FileDocument:
        pass

    @abstractmethod
    def _is_file(self, path: str) -> bool:
        pass

    @abstractmethod
    def _has_valid_extension(self, path: str) -> bool:
        pass

    @abstractmethod
    def _get_file_id(self, path: str) -> str:
        pass

    @abstractmethod
    def _walk_through_folder(self, path: str) -> List[str]:
        pass

    def _list_all_file_ids(self, path: str) -> List[str]:
        if self._is_file(path):
            file_id = self._get_file_id(path)
            if not self._has_valid_extension(file_id):
                raise ValueError(f"Invalid file extension for file: {path}")
            return [file_id]
        return self._walk_through_folder(path)

    def list_all_files_info(self) -> List[FileDocument]:
        LOGGER.info(f"Getting files info from {self.path}")
        file_info_list = []
        for file_path in self._list_all_file_ids(self.path):
            file_info_list.append(self._get_file_info(file_path))
        return file_info_list

    @abstractmethod
    def get_file_content(self, path: str) -> bytes:
        pass
