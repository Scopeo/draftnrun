import logging
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

from data_ingestion.document.folder_management.folder_management import FileDocument, FileDocumentType, FolderManager

LOGGER = logging.getLogger(__name__)


def _get_service_google_drive(access_token) -> Any:
    if not access_token:
        LOGGER.error("No access token provided.")
        raise ValueError("No access token provided.")

    creds = Credentials(token=access_token)
    service = build("drive", "v3", credentials=creds, cache_discovery=False)
    return service


class GoogleDriveFolderManager(FolderManager):
    def __init__(self, path: str, access_token: dict) -> None:
        super().__init__(path)
        self._cached_file_info = {}
        token = access_token.get("token") if isinstance(access_token, dict) else access_token
        self._service = _get_service_google_drive(token)

    def _is_file(self, path: str) -> bool:
        if path.startswith("https://drive.google.com/drive/folders/"):
            return False
        elif path.startswith("https://drive.google.com/file/d/"):
            return True
        else:
            raise ValueError(f"Invalid Google Drive path: {path}")

    def _get_file_id(self, path: str) -> str:
        return path.split("/")[-2]

    def _walk_through_folder(self, path: str) -> List[str]:
        folder_id = Path(path).name
        results = (
            self._service.files()
            .list(q=f"'{folder_id}' in parents", includeItemsFromAllDrives=True, supportsAllDrives=True)
            .execute()
        )
        files_in_folder = results.get("files", [])
        file_ids_list = []
        for file in files_in_folder:
            if file["mimeType"] == "application/vnd.google-apps.folder":
                subfolder_id = file["id"]
                subfolder_path = "https://drive.google.com/drive/folders/" + subfolder_id
                file_ids_list.extend(self._walk_through_folder(subfolder_path))
            elif self._has_valid_extension(file["id"]):
                file_ids_list.append(file["id"])
            else:
                continue
        return file_ids_list

    def _fetch_file_details(self, file_id: str) -> Dict[str, Any]:
        if file_id in self._cached_file_info:
            return self._cached_file_info[file_id]
        file = (
            self._service.files()
            .get(
                fileId=file_id, fields="id, name, mimeType, webViewLink, parents, modifiedTime", supportsAllDrives=True
            )
            .execute()
        )
        self._cached_file_info[file_id] = file
        return file

    def _has_valid_extension(self, path: str) -> bool:
        file = self._fetch_file_details(path)
        return Path(file["name"]).suffix in self.doc_possible_extensions

    def get_folder_names(self, file_id: str) -> list:
        folder_names = []
        parents = self._fetch_file_details(file_id).get("parents", [])
        while parents:
            folder_id = parents[0]
            folder_info = self._fetch_file_details(folder_id)
            folder_name = folder_info["name"]

            if folder_name != "My Drive":
                folder_names.append(folder_name)
            parents = folder_info.get("parents", [])

        return folder_names

    def _get_file_info(self, file_path: str) -> FileDocument:
        file = self._fetch_file_details(file_path)

        folder_names = self.get_folder_names(file["id"])

        # Get file type from MIME type with comprehensive logging
        mime_type = file["mimeType"]
        file_name = file["name"]
        from pathlib import Path

        file_extension = Path(file_name).suffix.lower()

        LOGGER.info(
            f"[GOOGLE_DRIVE] Processing file: '{file_name}', MIME type: '{mime_type}', Extension: '{file_extension}'"
        )

        file_type = FileDocumentType.from_mime_type(mime_type)

        if file_type is not None:
            LOGGER.info(
                f"[FILE_TYPE_DETECTION] Successfully mapped MIME type '{mime_type}' to file type "
                f"'{file_type.value}' for '{file_name}'"
            )
        else:
            LOGGER.warning(
                f"[FILE_TYPE_DETECTION] Unknown MIME type '{mime_type}' for file '{file_name}'. "
                f"Attempting fallback detection from extension '{file_extension}'"
            )
            # Try to determine type from file extension as fallback
            try:
                file_type = FileDocumentType(file_extension)
                LOGGER.info(
                    f"[FILE_TYPE_DETECTION] Successfully determined file type '{file_type.value}' "
                    f"from extension '{file_extension}' for '{file_name}'"
                )
            except ValueError:
                LOGGER.error(
                    f"[FILE_TYPE_DETECTION] FAILED - Could not determine file type for '{file_name}' "
                    f"with MIME type '{mime_type}' and extension '{file_extension}'"
                )
                raise ValueError(
                    f"Unsupported file type: MIME type '{mime_type}', "
                    f"extension '{file_extension}' for file '{file_name}'"
                )

        return FileDocument(
            id=file["id"],
            last_edited_ts=file.get("modifiedTime", None),
            type=file_type,
            file_name=file["name"],
            folder_name="/".join(reversed(folder_names)),
            metadata={
                "source_url": file.get("webViewLink", None),
            },
        )

    def get_file_content(self, file_id: str) -> bytes:
        file = self._fetch_file_details(file_id)
        file_type = FileDocumentType.from_mime_type(file["mimeType"])

        if file_type == FileDocumentType.GOOGLE_SHEET:
            export_mime = FileDocumentType.to_mime_type(FileDocumentType.EXCEL)
            request = self._service.files().export_media(fileId=file["id"], mimeType=export_mime)
        else:
            request = self._service.files().get_media(fileId=file["id"])

        fh = BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()
        return fh.getvalue()
