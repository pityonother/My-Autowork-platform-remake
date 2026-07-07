from __future__ import annotations

import asyncio
import io

import pytest
from fastapi import UploadFile

from app.shared.uploads import (
    UploadValidationError,
    read_upload_limited,
    safe_upload_filename,
    save_upload,
    validate_upload_extension,
)


def make_upload(filename: str, content: bytes = b"data") -> UploadFile:
    return UploadFile(filename=filename, file=io.BytesIO(content))


def test_safe_upload_filename_strips_path_traversal() -> None:
    assert safe_upload_filename("..\\secret/booking.xlsx") == "booking.xlsx"
    assert safe_upload_filename("\x00") == "upload"


def test_validate_upload_extension_rejects_unknown_suffix() -> None:
    with pytest.raises(UploadValidationError):
        validate_upload_extension(make_upload("booking.exe"), {".xlsx"})


def test_save_upload_limited_rejects_oversized_file(tmp_path) -> None:
    with pytest.raises(UploadValidationError):
        save_upload(
            "session",
            make_upload("large.xlsx", b"123456"),
            "booking",
            upload_root=tmp_path,
            max_bytes=5,
            allowed_suffixes={".xlsx"},
        )

    assert not list((tmp_path / "session").glob("*"))


def test_save_upload_limited_does_not_overwrite_same_name(tmp_path) -> None:
    first = save_upload("session", make_upload("booking.xlsx", b"first"), "booking", upload_root=tmp_path)
    second = save_upload("session", make_upload("booking.xlsx", b"second"), "booking", upload_root=tmp_path)

    assert first != second
    assert first.read_bytes() == b"first"
    assert second.read_bytes() == b"second"


def test_read_upload_limited_rejects_oversized_file() -> None:
    with pytest.raises(UploadValidationError):
        asyncio.run(read_upload_limited(make_upload("booking.xlsx", b"123456"), max_bytes=5, allowed_suffixes={".xlsx"}))
