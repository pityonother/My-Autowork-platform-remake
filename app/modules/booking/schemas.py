from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class BookingPreview:
    session_id: str
    supplier: str
    source_filename: str
    pack_filename: str
    rows: list[dict[str, Any]]
    columns: list[str]
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    detail_count: int = 0
    packadc_count: int = 0
    output_path: Path | None = None
    email_subject: str = ""
    mawb_no: str = ""
    purchaser: str = ""
    delivery_method: str = ""
    carrier_name: str = ""
    hbl_no: str = ""
    booking_date: str = ""
    delivery_to_hub_date: str = ""
    shipper: str = ""
    contact_person: str = "NA"
    tel: str = "NA"
    contact_email: str = "NA"
    pdf_page_count: int = 0
    validation_sections: list[Any] = field(default_factory=list)

    @property
    def validation_error_count(self) -> int:
        return sum(
            1
            for section in self.validation_sections
            for item in getattr(section, "items", [])
            if getattr(item, "status", "") == "error"
        )

    @property
    def validation_warning_count(self) -> int:
        return sum(
            1
            for section in self.validation_sections
            for item in getattr(section, "items", [])
            if getattr(item, "status", "") == "warning"
        )

    @property
    def can_generate(self) -> bool:
        return not self.errors and bool(self.rows) and self.validation_error_count == 0


@dataclass
class BookingEmailAttachment:
    filename: str
    path: Path
    content_type: str


__all__ = ["BookingEmailAttachment", "BookingPreview"]
