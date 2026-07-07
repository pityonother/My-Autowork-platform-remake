from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


@dataclass
class UfoIssueInput:
    short_cn: str
    short_en: str
    detail_en: str


@dataclass
class UfoAttachment:
    path: Path
    filename: str


@dataclass
class UfoMailInput:
    ufo_no: str
    to_email: str
    cc_email: str
    from_email: str
    issue_ids: Sequence[int]
    attachments: Sequence[UfoAttachment]


__all__ = ["UfoAttachment", "UfoIssueInput", "UfoMailInput"]
