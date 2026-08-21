from pathlib import Path
from uuid import UUID

from fastapi import UploadFile

from sms.core.config import settings
from sms.core.file_storage_exceptions import FileTooLargeError, InvalidFileTypeError

ALLOWED_CONTENT_TYPES = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}
MAX_UPLOAD_SIZE_BYTES = 5 * 1024 * 1024
_CHUNK_SIZE = 64 * 1024

# Magic-byte signatures, checked against the first chunk actually read —
# file.content_type is just the client-supplied multipart header, fully
# attacker-controlled, so it alone can't be trusted to gate what gets
# written to disk and served back from /uploads.
_JPEG_SIGNATURE = b"\xff\xd8\xff"
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_WEBP_RIFF_PREFIX = b"RIFF"
_WEBP_MARKER = b"WEBP"


def _detected_extension(first_chunk: bytes) -> str | None:
    if first_chunk.startswith(_JPEG_SIGNATURE):
        return "jpg"
    if first_chunk.startswith(_PNG_SIGNATURE):
        return "png"
    if first_chunk.startswith(_WEBP_RIFF_PREFIX) and first_chunk[8:12] == _WEBP_MARKER:
        return "webp"
    return None


async def save_profile_picture(file: UploadFile, *, subdir: str, entity_id: UUID) -> str:
    """Validates content-type and size, writes to a filename derived from
    entity_id (never the client-supplied filename — avoids path traversal
    and makes a re-upload a clean replace with no orphan bookkeeping),
    returns the relative path to store on the entity's
    profile_picture_path column."""
    declared_extension = ALLOWED_CONTENT_TYPES.get(file.content_type or "")
    if declared_extension is None:
        raise InvalidFileTypeError()

    first_chunk = await file.read(_CHUNK_SIZE)
    if _detected_extension(first_chunk) != declared_extension:
        raise InvalidFileTypeError()
    extension = declared_extension

    target_dir = Path(settings.upload_dir) / subdir
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / f"{entity_id}.{extension}"

    written = 0
    tmp_path = target_path.with_suffix(target_path.suffix + ".part")
    try:
        with tmp_path.open("wb") as out:
            chunk = first_chunk
            while chunk:
                written += len(chunk)
                if written > MAX_UPLOAD_SIZE_BYTES:
                    raise FileTooLargeError()
                out.write(chunk)
                chunk = await file.read(_CHUNK_SIZE)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise
    tmp_path.replace(target_path)

    return f"{subdir}/{entity_id}.{extension}"
