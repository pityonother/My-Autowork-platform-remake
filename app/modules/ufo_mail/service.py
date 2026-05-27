from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Sequence

from fastapi import UploadFile

from app.core.paths import APP_DIR, OUTPUT_DIR, UPLOAD_DIR
from app.modules.ufo_mail.cover_processor import is_supported_ufo_document
from app.modules.ufo_mail.rules import detect_ufo_no
from app.shared.uploads import save_upload
from app.modules.ufo_mail.legacy_adapter import (
    UfoAttachment,
    UfoMailInput,
    generate_ufo_eml,
    import_ufo_signature_from_eml,
)


YOLO_PYTHON_CANDIDATES = [
    APP_DIR / ".venv-yolo" / "Scripts" / "python.exe",
    APP_DIR / ".venv-yolo" / "bin" / "python",
]
ATTACHMENT_METADATA_FILENAME = "_ufo_attachments.json"


class LowConfidenceReviewRequired(ValueError):
    def __init__(self, *, session_id: str, review_reports: Sequence[str]) -> None:
        self.session_id = session_id
        self.review_reports = list(review_reports)
        joined = "；".join(self.review_reports)
        super().__init__(f"检测到低置信度 RH 候选框，需要先人工复核。报告：{joined}")


def safe_ufo_output_stem(value: str) -> str:
    text = (value or "").strip()
    match = re.search(r"\bUFO\d{6,}\b", text, flags=re.IGNORECASE)
    if match:
        return match.group(0).upper()
    safe = re.sub(r"[^A-Za-z0-9_-]+", "_", text).strip("_")
    return safe[:80] or "ufo_mail"


def unique_filename(filename: str, used_names: set[str]) -> str:
    path = Path(filename)
    stem = path.stem or "attachment"
    suffix = path.suffix
    candidate = filename
    index = 2
    while candidate.lower() in used_names:
        candidate = f"{stem}_{index}{suffix}"
        index += 1
    used_names.add(candidate.lower())
    return candidate


def resolve_yolo_python() -> Path:
    for candidate in YOLO_PYTHON_CANDIDATES:
        if candidate.exists():
            return candidate
    return Path(sys.executable)


def validate_session_id(session_id: str) -> str:
    session_id = session_id.strip()
    if not re.fullmatch(r"[0-9a-f]{12}", session_id):
        raise ValueError("UFO 处理会话编号不合法，请重新生成。")
    return session_id


def attachment_metadata_path(session_id: str) -> Path:
    return UPLOAD_DIR / validate_session_id(session_id) / ATTACHMENT_METADATA_FILENAME


def save_attachment_metadata(session_id: str, saved_attachments: Sequence[UfoAttachment]) -> None:
    metadata_path = attachment_metadata_path(session_id)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    payload = [
        {
            "path": str(attachment.path),
            "filename": attachment.filename,
        }
        for attachment in saved_attachments
    ]
    metadata_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_attachment_metadata(session_id: str) -> list[UfoAttachment]:
    session_id = validate_session_id(session_id)
    metadata_path = attachment_metadata_path(session_id)
    if not metadata_path.exists():
        raise ValueError("找不到上一次上传的附件记录，请重新选择附件生成。")

    upload_session_dir = (UPLOAD_DIR / session_id).resolve()
    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("附件记录无法读取，请重新选择附件生成。") from exc

    attachments: list[UfoAttachment] = []
    for item in payload:
        path = Path(str(item.get("path", ""))).resolve()
        filename = str(item.get("filename", "")).strip()
        if not path.is_relative_to(upload_session_dir):
            raise ValueError("附件记录路径不合法，请重新选择附件生成。")
        if not path.exists():
            raise ValueError("找不到上一次上传的附件文件，请重新选择附件生成。")
        attachments.append(UfoAttachment(path=path, filename=filename or path.name))
    return attachments


def clear_output_cache() -> dict[str, int]:
    output_dir = OUTPUT_DIR.resolve()
    runtime_dir = (APP_DIR / "runtime").resolve()
    if output_dir.name != "outputs" or output_dir.parent != runtime_dir:
        raise ValueError("输出缓存目录校验失败，已停止清理。")

    output_dir.mkdir(parents=True, exist_ok=True)
    deleted_files = 0
    deleted_dirs = 0
    for item in output_dir.iterdir():
        if item.is_symlink():
            item.unlink()
            deleted_files += 1
            continue
        is_junction = getattr(item, "is_junction", lambda: False)()
        if is_junction:
            item.rmdir()
            deleted_dirs += 1
            continue
        if item.is_dir():
            shutil.rmtree(item)
            deleted_dirs += 1
        else:
            item.unlink()
            deleted_files += 1
    return {"deleted_files": deleted_files, "deleted_dirs": deleted_dirs}


def run_ufo_cover_processor(
    *,
    input_path: Path,
    output_pdf: Path,
    ufo_no: str,
    report_json: Path,
    report_csv: Path,
    preview_dir: Path,
    result_json: Path,
) -> dict[str, object]:
    python_exe = resolve_yolo_python()
    command = [
        str(python_exe),
        "-m",
        "app.modules.ufo_mail.cover_processor",
        str(input_path),
        str(output_pdf),
        "--ufo-no",
        ufo_no,
        "--report-json",
        str(report_json),
        "--report-csv",
        str(report_csv),
        "--preview-dir",
        str(preview_dir),
        "--result-json",
        str(result_json),
    ]
    completed = subprocess.run(
        command,
        cwd=APP_DIR,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=600,
        check=False,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "unknown error").strip()
        raise ValueError(f"UFO PDF 自动遮盖失败：{detail[-1200:]}")
    if not result_json.exists():
        raise ValueError("UFO PDF 自动遮盖失败：未生成处理结果。")
    return json.loads(result_json.read_text(encoding="utf-8"))


def prepare_ufo_attachments(
    *,
    session_id: str,
    saved_attachments: Sequence[UfoAttachment],
    ufo_no: str,
    allow_low_confidence: bool = False,
) -> list[UfoAttachment]:
    output_dir = OUTPUT_DIR / "ufo_processed" / session_id
    used_names: set[str] = set()
    prepared: list[UfoAttachment] = []
    processed_index = 0
    review_reports: list[str] = []

    has_coverable_document = any(is_supported_ufo_document(item.path) for item in saved_attachments)
    has_pdf_document = any(item.path.suffix.lower() == ".pdf" for item in saved_attachments)
    if has_coverable_document and not ufo_no.strip():
        raise ValueError("请手工输入 UFO 编号；TIF/PDF 自动遮盖需要用这个编号替换首页 RH 编号。")

    for attachment in saved_attachments:
        if not is_supported_ufo_document(attachment.path):
            prepared.append(
                UfoAttachment(
                    path=attachment.path,
                    filename=unique_filename(attachment.filename, used_names),
                )
            )
            continue

        if has_pdf_document and attachment.path.suffix.lower() in {".tif", ".tiff"}:
            continue

        processed_index += 1
        stem = safe_ufo_output_stem(ufo_no)
        output_filename = unique_filename(f"{stem}.pdf" if processed_index == 1 else f"{stem}_{processed_index}.pdf", used_names)
        output_pdf = output_dir / output_filename
        report_json = output_dir / f"{Path(output_filename).stem}.cover_report.json"
        report_csv = output_dir / f"{Path(output_filename).stem}.cover_report.csv"
        result_json = output_dir / f"{Path(output_filename).stem}.result.json"
        preview_dir = output_dir / f"{Path(output_filename).stem}_preview"
        result = run_ufo_cover_processor(
            input_path=attachment.path,
            output_pdf=output_pdf,
            ufo_no=ufo_no,
            report_json=report_json,
            report_csv=report_csv,
            preview_dir=preview_dir,
            result_json=result_json,
        )
        review_count = int(result.get("review_count") or 0)
        if review_count:
            review_reports.append(str(report_csv))
        prepared.append(UfoAttachment(path=output_pdf, filename=output_filename))

    if review_reports and not allow_low_confidence:
        raise LowConfidenceReviewRequired(session_id=session_id, review_reports=review_reports)
    return prepared


def generate_mail_from_saved_attachments(
    *,
    session_id: str,
    saved_attachments: Sequence[UfoAttachment],
    issue_ids: Sequence[int],
    ufo_no: str,
    to_email: str,
    cc_email: str,
    from_email: str,
    allow_low_confidence: bool = False,
) -> Path:
    manual_ufo_no = ufo_no.strip()
    detected_ufo_no = manual_ufo_no or detect_ufo_no([item.filename for item in saved_attachments])
    final_attachments = prepare_ufo_attachments(
        session_id=session_id,
        saved_attachments=saved_attachments,
        ufo_no=manual_ufo_no,
        allow_low_confidence=allow_low_confidence,
    )
    output_stem = safe_ufo_output_stem(detected_ufo_no)
    output_name = f"{output_stem}_{session_id}.eml"
    output_path = OUTPUT_DIR / output_name
    if not output_path.resolve().is_relative_to(OUTPUT_DIR.resolve()):
        raise ValueError("输出文件名不合法。")
    generate_ufo_eml(
        UfoMailInput(
            ufo_no=detected_ufo_no,
            to_email=to_email,
            cc_email=cc_email,
            from_email=from_email,
            issue_ids=issue_ids,
            attachments=final_attachments,
        ),
        output_path,
    )
    return output_path


def generate_mail_from_saved_session(
    *,
    session_id: str,
    issue_ids: Sequence[int],
    ufo_no: str,
    to_email: str,
    cc_email: str,
    from_email: str,
    allow_low_confidence: bool = False,
) -> Path:
    session_id = validate_session_id(session_id)
    saved_attachments = load_attachment_metadata(session_id)
    return generate_mail_from_saved_attachments(
        session_id=session_id,
        saved_attachments=saved_attachments,
        issue_ids=issue_ids,
        ufo_no=ufo_no,
        to_email=to_email,
        cc_email=cc_email,
        from_email=from_email,
        allow_low_confidence=allow_low_confidence,
    )


def import_signature(signature_file: UploadFile, marker: str) -> None:
    session_id = uuid.uuid4().hex[:12]
    signature_path = save_upload(session_id, signature_file, "signature")
    import_ufo_signature_from_eml(signature_path, source_name=signature_file.filename, marker=marker)


def generate_mail(
    *,
    issue_ids: Sequence[int],
    attachments: Sequence[UploadFile],
    ufo_no: str,
    to_email: str,
    cc_email: str,
    from_email: str,
) -> Path:
    session_id = uuid.uuid4().hex[:12]
    saved_attachments: list[UfoAttachment] = []
    for idx, attachment in enumerate(attachments, start=1):
        if not attachment.filename:
            continue
        saved_path = save_upload(session_id, attachment, f"ufo_attachment_{idx:03d}")
        saved_attachments.append(UfoAttachment(path=saved_path, filename=attachment.filename))

    manual_ufo_no = ufo_no.strip()
    save_attachment_metadata(session_id, saved_attachments)
    return generate_mail_from_saved_attachments(
        session_id=session_id,
        saved_attachments=saved_attachments,
        issue_ids=issue_ids,
        ufo_no=manual_ufo_no,
        to_email=to_email,
        cc_email=cc_email,
        from_email=from_email,
    )
