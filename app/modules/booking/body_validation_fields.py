from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from booking_rules.common import PURCHASER_BY_PO_PREFIX


@dataclass(frozen=True)
class BookingBodyField:
    code: str
    label: str
    column_letter: str


BODY_FIELDS = [
    BookingBodyField("Line", "Line", "A"),
    BookingBodyField("case_number", "Case number", "B"),
    BookingBodyField("PO_No", "PO No.", "C"),
    BookingBodyField("Customer_Part_No", "PN / Customer Part No.", "D"),
    BookingBodyField("Part_Description", "Part Description", "E"),
    BookingBodyField("Quantity", "Quantity", "F"),
    BookingBodyField("unit", "Unit", "G"),
    BookingBodyField("Pkgs", "Cartons", "H"),
    BookingBodyField("FJZ", "N.Wt", "I"),
    BookingBodyField("G_Wt", "G.Wt", "J"),
    BookingBodyField("CBM", "CBM", "K"),
    BookingBodyField("Pallet", "Pallet", "L"),
    BookingBodyField("Invoice_No", "Invoice No.", "M"),
    BookingBodyField("madeDate", "Production date", "N"),
    BookingBodyField("Invoice_Date", "Invoice Date", "O"),
    BookingBodyField("Made_In", "Made In", "P"),
    BookingBodyField("Batch_No", "Batch No.", "Q"),
    BookingBodyField("ASN", "Delivery Schedule Number", "R"),
    BookingBodyField("gyskbh", "Supplier card number", "S"),
    BookingBodyField("packing", "Supplier delivery note number", "T"),
    BookingBodyField("Tray_Type", "Tray Type", "U"),
    BookingBodyField("brand", "Brand", "V"),
    BookingBodyField("LEDBinCode", "LEDBinCode", "W"),
    BookingBodyField("min_package", "Min package", "X"),
    BookingBodyField("per_box", "Standard quantity per box", "Y"),
    BookingBodyField("IPPC", "IPPC", "Z"),
    BookingBodyField("Remark", "Remark", "AA"),
]

FIELDS_BY_CODE = {field.code: field for field in BODY_FIELDS}
REQUIRED_FIELDS = {
    "case_number",
    "PO_No",
    "Customer_Part_No",
    "Part_Description",
    "Quantity",
    "unit",
    "Pkgs",
    "FJZ",
    "G_Wt",
    "CBM",
    "Pallet",
    "Invoice_No",
    "madeDate",
    "Made_In",
    "Batch_No",
    "packing",
    "brand",
    "LEDBinCode",
    "min_package",
    "per_box",
}
ALLOW_ZERO_NUMERIC_FIELDS = {"Pkgs", "FJZ", "G_Wt", "CBM", "Pallet", "min_package"}
INTEGER_FIELDS = {"Pkgs", "Pallet"}
KNOWN_PO_PREFIXES = set(PURCHASER_BY_PO_PREFIX)
POSITIVE_WEIGHT_PO_PREFIXES = KNOWN_PO_PREFIXES | {"E330"}
FALLBACK_COUNTRY_KEYS = {
    "CN",
    "CHINA",
    "HK",
    "HONGKONG",
    "US",
    "USA",
    "UNITEDSTATES",
    "JP",
    "JAPAN",
    "KR",
    "KOREA",
    "REPUBLICOFKOREA",
    "MY",
    "MALAYSIA",
    "PH",
    "PHILIPPINES",
    "SG",
    "SINGAPORE",
    "TH",
    "THAILAND",
    "TW",
    "TAIWAN",
    "VN",
    "VIETNAM",
}
SPECIAL_COUNTRY_KEYS = {"TW,CN", "TAIWAN,CHINA"}
NUMERIC_FIELD_CODES = {"Quantity", "Pkgs", "FJZ", "G_Wt", "CBM", "Pallet", "min_package", "per_box"}
UNIT_NORMALIZABLE_NUMERIC_FIELDS = NUMERIC_FIELD_CODES - {"per_box"}
MANUAL_REVIEW_NA_FIELDS = {"Pkgs", "FJZ", "G_Wt", "CBM", "min_package"}
WEIGHT_AVERAGE_SCALE = Decimal("0.001")
SIL_FUCA_DYNAMIC_PO_PREFIXES = KNOWN_PO_PREFIXES
