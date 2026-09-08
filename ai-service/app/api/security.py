"""Upload security hygiene (Phase 10 section 32).

Validated BEFORE any parsing/processing touches the file: extension,
declared size, and filename safety (no path separators, no traversal
sequences, no null bytes). This does not replace `DocumentIngestionService`'s
own "no usable text" check -- it only rejects unsafe or oversized uploads
before they reach the pipeline at all.
"""
from __future__ import annotations

from app.core.config import Settings
from app.core.exceptions import InvalidUploadError

_UNSAFE_FILENAME_CHARS = ("/", "\\", "\x00")


def validate_upload_filename(filename: str | None) -> str:
    if not filename or not filename.strip():
        raise InvalidUploadError("Uploaded file has no filename.")
    if any(ch in filename for ch in _UNSAFE_FILENAME_CHARS):
        raise InvalidUploadError("Uploaded filename contains unsafe path characters.")
    if ".." in filename:
        raise InvalidUploadError("Uploaded filename must not contain '..' (path traversal).")
    return filename


def validate_upload_extension(filename: str, settings: Settings) -> None:
    suffix = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if suffix not in settings.allowed_upload_extensions:
        allowed = ", ".join(settings.allowed_upload_extensions)
        raise InvalidUploadError(f"Unsupported file type '{suffix or '(none)'}'. Allowed: {allowed}.")


def validate_upload_size(size_bytes: int, settings: Settings) -> None:
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    if size_bytes <= 0:
        raise InvalidUploadError("Uploaded file is empty.")
    if size_bytes > max_bytes:
        raise InvalidUploadError(f"Uploaded file ({size_bytes} bytes) exceeds the {settings.max_upload_size_mb}MB limit.")


def validate_upload(filename: str | None, size_bytes: int, settings: Settings) -> str:
    """Runs every check and returns the validated filename, or raises
    `InvalidUploadError`."""
    safe_filename = validate_upload_filename(filename)
    validate_upload_extension(safe_filename, settings)
    validate_upload_size(size_bytes, settings)
    return safe_filename
