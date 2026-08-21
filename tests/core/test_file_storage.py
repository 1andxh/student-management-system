"""Direct unit tests for sms.core.file_storage.save_profile_picture — no DB,
no HTTP, just the content-type/size-limit/path-derivation behavior the
contract for this stage describes. settings.upload_dir is monkeypatched to a
pytest tmp_path in every test here so nothing touches the real uploads/
directory or leaves files behind.

Payloads use real magic-byte signatures (minimal valid JPEG/PNG/WebP
headers, not full valid images) rather than arbitrary placeholder bytes —
save_profile_picture verifies the actual file content against its declared
Content-Type, not just the header, so a fake-content upload with a real
content-type would now be correctly rejected as a mismatch.

Exception names (InvalidFileTypeError / FileTooLargeError) and their module
location are this test file's own best-guess at the contract's open "your
call" on structure, since the plan text only fixes their status codes (415 /
413) and existence, not their exact names/location. If the production
implementation lands with different names, only the imports below need to
change to match — the test bodies exercise observable behavior (status code,
returned path, bytes on disk), not the exception class identity itself.
"""

import io
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import UploadFile
from starlette.datastructures import Headers

from sms.core import file_storage
from sms.core.config import settings
from sms.core.file_storage_exceptions import FileTooLargeError, InvalidFileTypeError

# Minimal real magic-byte prefixes for each allowed type, followed by
# arbitrary body bytes — enough for save_profile_picture's signature check
# to recognize them, not full valid decodable images.
JPEG_BYTES = b"\xff\xd8\xff" + b"fake-jpeg-body"
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"fake-png-body"
WEBP_BYTES = b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"fake-webp-body"


def make_upload_file(
    content: bytes, content_type: str, filename: str = "photo.jpg"
) -> UploadFile:
    return UploadFile(
        io.BytesIO(content), filename=filename, headers=Headers({"content-type": content_type})
    )


def _signed_payload(signature: bytes, total_size: int) -> bytes:
    """A payload starting with a real magic-byte signature, padded with
    filler bytes to exactly total_size — used by the size-limit tests,
    which need to exercise the size check specifically, not the
    content-sniffing check."""
    assert total_size >= len(signature)
    return signature + b"x" * (total_size - len(signature))


@pytest.fixture(autouse=True)
def _upload_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    return tmp_path


async def test_save_profile_picture_success_jpeg(tmp_path: Path) -> None:
    entity_id = uuid4()
    upload = make_upload_file(JPEG_BYTES, "image/jpeg")

    relative_path = await file_storage.save_profile_picture(
        upload, subdir="students", entity_id=entity_id
    )

    assert relative_path == f"students/{entity_id}.jpg"
    saved = tmp_path / relative_path
    assert saved.exists()
    assert saved.read_bytes() == JPEG_BYTES


async def test_save_profile_picture_success_png(tmp_path: Path) -> None:
    entity_id = uuid4()
    upload = make_upload_file(PNG_BYTES, "image/png", filename="photo.png")

    relative_path = await file_storage.save_profile_picture(
        upload, subdir="teachers", entity_id=entity_id
    )

    assert relative_path == f"teachers/{entity_id}.png"
    assert (tmp_path / relative_path).read_bytes() == PNG_BYTES


async def test_save_profile_picture_success_webp(tmp_path: Path) -> None:
    entity_id = uuid4()
    upload = make_upload_file(WEBP_BYTES, "image/webp", filename="photo.webp")

    relative_path = await file_storage.save_profile_picture(
        upload, subdir="students", entity_id=entity_id
    )

    assert relative_path == f"students/{entity_id}.webp"


async def test_save_profile_picture_creates_missing_subdir(tmp_path: Path) -> None:
    assert not (tmp_path / "students").exists()
    entity_id = uuid4()
    upload = make_upload_file(JPEG_BYTES, "image/jpeg")

    await file_storage.save_profile_picture(upload, subdir="students", entity_id=entity_id)

    assert (tmp_path / "students").is_dir()


async def test_save_profile_picture_uses_entity_id_not_client_filename(tmp_path: Path) -> None:
    # The stored filename must be derived from entity_id + the content-type's
    # implied extension, never the client-supplied filename — using the raw
    # client filename would allow path traversal (e.g. "../../evil.jpg").
    entity_id = uuid4()
    upload = make_upload_file(JPEG_BYTES, "image/jpeg", filename="../../../etc/passwd.jpg")

    relative_path = await file_storage.save_profile_picture(
        upload, subdir="students", entity_id=entity_id
    )

    assert relative_path == f"students/{entity_id}.jpg"
    assert (tmp_path / "students" / f"{entity_id}.jpg").exists()


async def test_save_profile_picture_rejects_invalid_content_type(tmp_path: Path) -> None:
    upload = make_upload_file(b"not an image", "application/pdf", filename="doc.pdf")

    with pytest.raises(InvalidFileTypeError) as exc_info:
        await file_storage.save_profile_picture(upload, subdir="students", entity_id=uuid4())

    assert exc_info.value.status_code == 415
    # Nothing should be written to disk for a rejected upload.
    assert list(tmp_path.rglob("*")) == [] or not any(
        p.is_file() for p in tmp_path.rglob("*")
    )


async def test_save_profile_picture_rejects_content_type_spoofing(tmp_path: Path) -> None:
    # Declares image/jpeg but the actual bytes are plain text — the
    # Content-Type header alone is fully client-controlled and must not be
    # trusted; the real file content has to back it up.
    upload = make_upload_file(b"<script>alert(1)</script>", "image/jpeg")

    with pytest.raises(InvalidFileTypeError) as exc_info:
        await file_storage.save_profile_picture(upload, subdir="students", entity_id=uuid4())

    assert exc_info.value.status_code == 415
    assert not any(p.is_file() for p in tmp_path.rglob("*"))


async def test_save_profile_picture_rejects_oversized_file(tmp_path: Path) -> None:
    oversized = _signed_payload(b"\xff\xd8\xff", file_storage.MAX_UPLOAD_SIZE_BYTES + 1)
    upload = make_upload_file(oversized, "image/jpeg")

    with pytest.raises(FileTooLargeError) as exc_info:
        await file_storage.save_profile_picture(upload, subdir="students", entity_id=uuid4())

    assert exc_info.value.status_code == 413


async def test_save_profile_picture_accepts_file_exactly_at_max_size(tmp_path: Path) -> None:
    exact = _signed_payload(b"\xff\xd8\xff", file_storage.MAX_UPLOAD_SIZE_BYTES)
    entity_id = uuid4()
    upload = make_upload_file(exact, "image/jpeg")

    relative_path = await file_storage.save_profile_picture(
        upload, subdir="students", entity_id=entity_id
    )

    assert (tmp_path / relative_path).stat().st_size == file_storage.MAX_UPLOAD_SIZE_BYTES


def test_allowed_content_types_matches_contract() -> None:
    assert set(file_storage.ALLOWED_CONTENT_TYPES) == {"image/jpeg", "image/png", "image/webp"}


def test_max_upload_size_bytes_matches_contract() -> None:
    assert file_storage.MAX_UPLOAD_SIZE_BYTES == 5 * 1024 * 1024
