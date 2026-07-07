from __future__ import annotations

import os
from pathlib import Path

from fastapi import UploadFile

from app.core.paths import UPLOAD_DIR


MAX_UPLOAD_BYTES_ENV = "MY_AUTOWORK_MAX_UPLOAD_BYTES"
DEFAULT_MAX_UPLOAD_BYTES = 30 * 1024 * 1024
_CHUNK_SIZE = 1024 * 1024


class UploadValidationError(ValueError):
    pass


def max_upload_bytes() -> int:
    raw = os.environ.get(MAX_UPLOAD_BYTES_ENV, "").strip()
    if not raw:
        return DEFAULT_MAX_UPLOAD_BYTES
    try:
        value = int(raw)
    except ValueError as exc:
        raise UploadValidationError(f"{MAX_UPLOAD_BYTES_ENV} must be an integer.") from exc
    if value <= 0:
        raise UploadValidationError(f"{MAX_UPLOAD_BYTES_ENV} must be greater than 0.")
    return value


def safe_upload_filename(filename: str | None) -> str:
    name = str(filename or "upload").replace("\\", "/").split("/")[-1].strip()
    name = name.replace("\x00", "")
    return name or "upload"


def _normalized_suffixes(allowed_suffixes: set[str] | frozenset[str] | None) -> set[str]:
    if not allowed_suffixes:
        return set()
    return {suffix.lower() if suffix.startswith(".") else f".{suffix.lower()}" for suffix in allowed_suffixes}


def validate_upload_extension(uploaded: UploadFile, allowed_suffixes: set[str] | frozenset[str] | None) -> None:
    suffixes = _normalized_suffixes(allowed_suffixes)
    if not suffixes:
        return
    filename = safe_upload_filename(uploaded.filename)
    suffix = Path(filename).suffix.lower()
    if suffix not in suffixes:
        allowed = ", ".join(sorted(suffixes))
        raise UploadValidationError(f"Unsupported upload type for {filename}; allowed suffixes: {allowed}.")


def unique_upload_path(target_dir: Path, filename: str) -> Path:
    candidate = target_dir / filename
    if not candidate.exists():
        return candidate
    path = Path(filename)
    stem = path.stem or "upload"
    suffix = path.suffix
    index = 2
    while True:
        candidate = target_dir / f"{stem}_{index}{suffix}"
        if not candidate.exists():
            return candidate
        index += 1


def save_upload(
    session_id: str,
    uploaded: UploadFile,
    prefix: str,
    upload_root: Path = UPLOAD_DIR,
    *,
    max_bytes: int | None = None,
    allowed_suffixes: set[str] | frozenset[str] | None = None,
) -> Path:
    validate_upload_extension(uploaded, allowed_suffixes)
    limit = max_bytes if max_bytes is not None else max_upload_bytes()
    target_dir = upload_root / session_id
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = unique_upload_path(target_dir, f"{prefix}_{safe_upload_filename(uploaded.filename)}")
    written = 0
    uploaded.file.seek(0)
    with target_path.open("wb") as buffer:
        while True:
            chunk = uploaded.file.read(_CHUNK_SIZE)
            if not chunk:
                break
            written += len(chunk)
            if written > limit:
                buffer.close()
                target_path.unlink(missing_ok=True)
                raise UploadValidationError(f"Upload is larger than the {limit} byte limit.")
            buffer.write(chunk)
    return target_path


async def read_upload_limited(
    uploaded: UploadFile,
    *,
    max_bytes: int | None = None,
    allowed_suffixes: set[str] | frozenset[str] | None = None,
) -> bytes:
    validate_upload_extension(uploaded, allowed_suffixes)
    limit = max_bytes if max_bytes is not None else max_upload_bytes()
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await uploaded.read(_CHUNK_SIZE)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise UploadValidationError(f"Upload is larger than the {limit} byte limit.")
        chunks.append(chunk)
    return b"".join(chunks)
