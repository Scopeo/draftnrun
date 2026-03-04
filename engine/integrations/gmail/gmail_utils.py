import base64
import mimetypes
from email.message import EmailMessage
from pathlib import Path
from typing import Iterable, Optional

from engine.temps_folder_utils import get_output_dir


def _ensure_paths(attachments: Optional[Iterable[str | Path]]) -> list[Path]:
    output_dir = get_output_dir()
    if not attachments:
        return []
    paths: list[Path] = []
    for att in attachments:
        p = output_dir / Path(att)
        if not p.is_file():
            raise FileNotFoundError(f"Attachment not found or not a file: {p}")
        paths.append(p)
    return paths


def _guess_mimetype(path: Path) -> tuple[str, str]:
    mime, _ = mimetypes.guess_type(path.name)
    if not mime:
        return "application", "octet-stream"
    maintype, subtype = mime.split("/", 1)
    return maintype, subtype


def create_raw_mail_message(
    subject: str,
    body: str,
    sender_email_address: str,
    recipients: Optional[list[str]] = None,
    cc: Optional[list[str]] = None,
    bcc: Optional[list[str]] = None,
    attachments: Optional[Iterable[str | Path]] = None,
) -> dict:
    message = EmailMessage()
    message.set_content(body)
    message["Subject"] = subject
    message["From"] = sender_email_address
    if recipients:
        message["To"] = ", ".join(recipients)
    if cc:
        message["Cc"] = ", ".join(cc)
    if bcc:
        message["Bcc"] = ", ".join(bcc)
    for path in _ensure_paths(attachments):
        maintype, subtype = _guess_mimetype(path)
        data = path.read_bytes()
        message.add_attachment(
            data,
            maintype=maintype,
            subtype=subtype,
            filename=path.name,
        )
    encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
    return {"raw": encoded_message}
