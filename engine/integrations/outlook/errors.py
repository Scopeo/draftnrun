class OutlookError(Exception):
    """Base exception for Outlook integration errors."""


class OutlookAPIError(OutlookError):
    """Raised when a Microsoft Graph API call fails."""

    def __init__(self, operation: str, status_code: int):
        self.operation = operation
        self.status_code = status_code
        super().__init__(f"Failed to {operation}: HTTP {status_code}")


class AttachmentPathError(OutlookError):
    """Raised when an attachment path escapes the allowed output directory."""

    def __init__(self, path: str):
        self.path = path
        super().__init__(f"Attachment path escapes the output directory: {path!r}")


class AttachmentNotFoundError(OutlookError):
    """Raised when an attachment file does not exist or is not a regular file."""

    def __init__(self, path: str):
        self.path = path
        super().__init__(f"Attachment not found or not a file: {path}")


class AttachmentTooLargeError(OutlookError):
    """Raised when an attachment exceeds the Graph API inline size limit."""

    def __init__(self, filename: str, size_bytes: int, limit_bytes: int):
        self.filename = filename
        self.size_bytes = size_bytes
        self.limit_bytes = limit_bytes
        size_mb = size_bytes / (1024 * 1024)
        limit_mb = limit_bytes / (1024 * 1024)
        super().__init__(
            f"Attachment '{filename}' is {size_mb:.1f} MB, which exceeds "
            f"the {limit_mb:.0f} MB limit for Microsoft Graph inline attachments. "
            f"Large file attachments via upload sessions are not yet supported."
        )
