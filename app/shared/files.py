from __future__ import annotations

from pathlib import Path

from fastapi.responses import FileResponse


EXCEL_XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
EXCEL_XLS_MEDIA_TYPE = "application/vnd.ms-excel"
EML_MEDIA_TYPE = "message/rfc822"


def safe_download_filename(filename: str) -> str:
    name = filename.replace("\\", "/").split("/")[-1].replace("\x00", "").strip()
    return name or "download"


def excel_download(path: Path, filename: str | None = None) -> FileResponse:
    return FileResponse(path, media_type=EXCEL_XLSX_MEDIA_TYPE, filename=safe_download_filename(filename or path.name))


def legacy_excel_download(path: Path, filename: str | None = None) -> FileResponse:
    return FileResponse(path, media_type=EXCEL_XLS_MEDIA_TYPE, filename=safe_download_filename(filename or path.name))


def eml_download(path: Path, filename: str | None = None) -> FileResponse:
    return FileResponse(path, media_type=EML_MEDIA_TYPE, filename=safe_download_filename(filename or path.name))
