from __future__ import annotations

from pathlib import Path
from typing import Any


def build_ufo_subject(ufo_no: str, issues: list[dict[str, Any]]) -> str:
    from app.modules.ufo_mail.legacy_adapter import build_ufo_subject as legacy_build_ufo_subject

    return legacy_build_ufo_subject(ufo_no, issues)


def generate_ufo_eml(mail_input: Any, output_path: Path) -> str:
    from app.modules.ufo_mail.legacy_adapter import generate_ufo_eml as legacy_generate_ufo_eml

    return legacy_generate_ufo_eml(mail_input, output_path)


__all__ = ["build_ufo_subject", "generate_ufo_eml"]
