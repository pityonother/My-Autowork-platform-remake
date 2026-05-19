from __future__ import annotations

import re
from collections.abc import Sequence


def detect_ufo_no(filenames: Sequence[str]) -> str:
    for filename in filenames:
        match = re.search(r"\b(UFO\d{6,})", filename, flags=re.IGNORECASE)
        if match:
            return match.group(1).upper()
    return ""


__all__ = ["detect_ufo_no"]
