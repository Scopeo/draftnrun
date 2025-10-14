import logging
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse, unquote

from data_ingestion.boto3_client import get_s3_boto3_client, get_content_from_file
from engine.temps_folder_utils import get_output_dir

LOGGER = logging.getLogger(__name__)


def load_file_from_s3(s3_url: str, output_path: Optional[str] = None) -> str:
    try:
        parsed_url = urlparse(s3_url)

        if not parsed_url.netloc or not parsed_url.path:
            raise ValueError(f"URL S3 invalide: {s3_url}")
        hostname_parts = parsed_url.netloc.split(".")
        if len(hostname_parts) < 3 or "s3" not in hostname_parts:
            raise ValueError(f"Format d'URL S3 non reconnu: {s3_url}")

        bucket_name = hostname_parts[0]
        key = unquote(parsed_url.path.lstrip("/"))
        key = key.replace("+", " ")

        LOGGER.info(f"Téléchargement du fichier S3 - Bucket: {bucket_name}, Key: {key}")
        s3_client = get_s3_boto3_client()
        file_content = get_content_from_file(s3_client, bucket_name, key)

        if file_content is None:
            raise ValueError(f"Impossible de récupérer le fichier {key} depuis le bucket {bucket_name}")

        if output_path is None:
            filename = Path(key).name
            output_dir = get_output_dir()
            output_path = output_dir / filename
        else:
            output_path = Path(output_path)

        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "wb") as f:
            f.write(file_content)

        LOGGER.info(f"Fichier téléchargé avec succès: {output_path}")
        return str(output_path)

    except Exception as e:
        error_msg = f"Erreur lors du téléchargement du fichier S3 {s3_url}: {str(e)}"
        LOGGER.error(error_msg)
        raise ValueError(error_msg)
