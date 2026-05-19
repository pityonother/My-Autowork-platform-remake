from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import UploadFile

from app.core.paths import UPLOAD_DIR


def safe_upload_filename(filename: str | None) -> str:
    name = str(filename or "upload").replace("\\", "/").split("/")[-1].strip()
    name = name.replace("\x00", "")
    return name or "upload"


def save_upload(
    session_id: str,
    uploaded: UploadFile,
    prefix: str,
    upload_root: Path = UPLOAD_DIR,
) -> Path:
    target_dir = upload_root / session_id
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / f"{prefix}_{safe_upload_filename(uploaded.filename)}"
    with target_path.open("wb") as buffer:
        shutil.copyfileobj(uploaded.file, buffer)
    return target_path
