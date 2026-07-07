from __future__ import annotations

from pathlib import Path
from typing import Any


def import_ufo_signature_from_eml(path: Path, *, source_name: str, marker: str) -> dict[str, Any]:
    from app.modules.ufo_mail.legacy_adapter import (
        import_ufo_signature_from_eml as legacy_import_ufo_signature_from_eml,
    )

    return legacy_import_ufo_signature_from_eml(path, source_name=source_name, marker=marker)


def strip_forwarded_history(html: str, plain: str) -> tuple[str, str]:
    from app.modules.ufo_mail.legacy_adapter import strip_forwarded_history as legacy_strip_forwarded_history

    return legacy_strip_forwarded_history(html, plain)


__all__ = ["import_ufo_signature_from_eml", "strip_forwarded_history"]
