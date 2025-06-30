from pathlib import Path
from typing import List

from data_ingestion.document.folder_management.folder_management import FileDocument, FileDocumentType, FolderManager
from data_ingestion.boto3_client import get_s3_boto3_client, get_content_from_file, delete_file_from_bucket
from settings import settings


class S3FolderManager(FolderManager):
    def __init__(
        self,
        folder_payload: list[dict],
        bucket_name: str = settings.S3_BUCKET_NAME,
        s3_url_endpoint: str = settings.S3_ENDPOINT_URL,
        s3_access_key_id: str = settings.S3_ACCESS_KEY_ID,
        s3_secret_access_key: str = settings.S3_SECRET_ACCESS_KEY,
        s3_region_name: str = settings.S3_REGION_NAME,
    ) -> None:
        super().__init__("dummy_path")
        self._bucket_name = bucket_name
        self._s3_url_endpoint = s3_url_endpoint
        self._s3_access_key_id = s3_access_key_id
        self._s3_secret_access_key = s3_secret_access_key
        self._s3_region_name = s3_region_name
        self.s3_client = get_s3_boto3_client(
            endpoint_url=self._s3_url_endpoint,
            aws_access_key_id=self._s3_access_key_id,
            aws_secret_access_key=self._s3_secret_access_key,
            region_name=self._s3_region_name,
        )
        self._files = {
            f["path"]: {
                "name": f["name"],
                "last_edited_ts": f.get("last_edited_ts", None),
                "s3_path": f.get("s3_path", None),
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
        s3_path_to_file = self._files[file_path]["s3_path"]
        return get_content_from_file(self.s3_client, self._bucket_name, s3_path_to_file)

    def clean_bucket(self) -> None:
        """Delete all files in the S3 bucket."""
        for file_path in self._files:
            s3_path_to_file = self._files[file_path]["s3_path"]
            if s3_path_to_file:
                delete_file_from_bucket(s3_client=self.s3_client, bucket_name=self._bucket_name, key=s3_path_to_file)
