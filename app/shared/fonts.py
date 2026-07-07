from __future__ import annotations

import os
from pathlib import Path

from app.shared.lazy_imports import lazy_module


ImageFont = lazy_module("PIL.ImageFont")


FONT_PATH_ENV = "MY_AUTOWORK_FONT_PATH"

_FONT_CANDIDATES = [
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/simhei.ttf",
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
]


def load_preferred_font(size: int) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    configured_path = os.environ.get(FONT_PATH_ENV, "").strip()
    candidates = [configured_path, *_FONT_CANDIDATES] if configured_path else _FONT_CANDIDATES
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate)
        if not path.is_file():
            continue
        try:
            return ImageFont.truetype(str(path), size)
        except OSError:
            continue
    return ImageFont.load_default()


def font_text_height(font: ImageFont.ImageFont | ImageFont.FreeTypeFont, sample: str = "A") -> int:
    left, top, right, bottom = font.getbbox(sample)
    return max(1, bottom - top)
