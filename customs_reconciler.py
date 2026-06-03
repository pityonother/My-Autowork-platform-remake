from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from app.shared.lazy_imports import lazy_module
from app.shared.performance import cached_file_result
from invoice_reconciler import (
    normalize_customer_order_no,
    parse_decimal_value,
    parse_source_file,
)

openpyxl = lazy_module("openpyxl")
pd = lazy_module("pandas")


USD_TO_HKD = Decimal("7.85")
SMOOTH_HANDLING_FEE = Decimal("10.00")
DECLARATION_FEE_MIN = Decimal("16.5")
DECLARATION_FEE_MAX = Decimal("216.3")
DECLARATION_FEE_BASE = Decimal("16.3")
DECLARATION_FEE_THRESHOLD = Decimal("46000")
DECLARATION_FEE_RATE = Decimal("0.000125")
PRODUCT_NAME_BY_CODE = {
    "8504409999": "充电器（电动车用）",
}


@dataclass
class CustomsSourceSummary:
    customer_order_no: str
    total_cartons: Decimal
    total_pcs: Decimal
    total_pallets: Decimal
    total_gross_weight: Decimal
    total_amount_usd: Decimal
    total_amount_hkd: Decimal
    product_names: List[str]
    commodity_codes: List[str]
    tan_nos: List[str]


@dataclass
class CustomsPreviewRow:
    customer_order_no: str
    transport_no: str
    ship_date: datetime
    ship_date_label: str
    hk_plate: str
    seamless_no: str
    total_cartons: Decimal
    total_pcs: Decimal
    total_pallets: Decimal
    total_gross_weight: Decimal
    total_amount_usd: Decimal
    total_amount_hkd: Decimal
    product_names: List[str]
    commodity_codes: List[str]
    tan_nos: List[str]
    declaration_fee: Decimal
    declaration_fee_formula: str = ""
    warnings: List[str] | None = None

    def to_preview(self) -> Dict[str, Any]:
        return {
            "customer_order_no": self.customer_order_no,
            "transport_no": self.transport_no,
            "ship_date": self.ship_date.strftime("%Y-%m-%d"),
            "ship_date_label": self.ship_date_label,
            "hk_plate": self.hk_plate,
            "seamless_no": self.seamless_no,
            "seamless_no_display": self.seamless_no,
            "total_cartons": float(self.total_cartons),
            "total_cartons_display": format_whole_number(self.total_cartons),
            "total_pcs": float(self.total_pcs),
            "total_pcs_display": format_whole_number(self.total_pcs),
            "total_pallets": float(self.total_pallets),
            "total_pallets_display": format_whole_number(self.total_pallets),
            "total_gross_weight": float(self.total_gross_weight),
            "total_amount_usd": float(self.total_amount_usd),
            "total_amount_hkd": float(self.total_amount_hkd),
            "product_names": self.product_names,
            "commodity_codes": self.commodity_codes,
            "tan_nos": self.tan_nos,
            "declaration_fee": float(self.declaration_fee),
            "declaration_fee_display": format_money(self.declaration_fee),
            "declaration_fee_formula": self.declaration_fee_formula,
            "warnings": self.warnings or [],
        }


@dataclass
class CustomsOutput:
    preview_rows: List[Dict[str, Any]]
    errors: List[str]
    preview_export_path: Optional[Path]
    bill_output_path: Optional[Path]


def quantized(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def format_whole_number(value: Decimal) -> str:
    return str(int(value))


def format_money(value: Decimal) -> str:
    return f"{quantized(value):.2f}"


def normalize_identifier(value: object) -> str:
    if value is None:
        return ""
    if not isinstance(value, str) and pd.isna(value):
        return ""
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return format(value, "f").rstrip("0").rstrip(".")
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return ""
    if text.endswith(".0"):
        prefix = text[:-2]
        if prefix.replace("-", "").isdigit():
            return prefix
    return text


def load_excel_file(path: Path) -> tuple[pd.ExcelFile, str]:
    last_error: Optional[Exception] = None
    for engine in ["openpyxl", "xlrd"]:
        try:
            return pd.ExcelFile(path, engine=engine), engine
        except Exception as exc:  # noqa: BLE001
            last_error = exc
    assert last_error is not None
    raise last_error


def normalize_header_name(value: object) -> str:
    return str(value or "").strip().replace("\n", "").replace(" ", "").lower()


def parse_order_management(path: Path) -> Dict[str, Dict[str, Any]]:
    return cached_file_result(
        "customs.parse_order_management",
        path,
        lambda: _parse_order_management_uncached(path),
    )


def _parse_order_management_uncached(path: Path) -> Dict[str, Dict[str, Any]]:
    excel_file, _ = load_excel_file(path)
    df = excel_file.parse(excel_file.sheet_names[0])

    header_aliases = {
        "customer_order_no": {"客户订单号"},
        "transport_no": {"主单号"},
        "job_date": {"作业日期"},
        "hk_plate": {"车牌"},
        "seamless_no": {"无缝号"},
    }
    normalized_columns = {
        normalize_header_name(column): column for column in df.columns
    }

    def pick_column(field: str) -> Optional[str]:
        for alias in header_aliases[field]:
            actual = normalized_columns.get(normalize_header_name(alias))
            if actual is not None:
                return actual
        return None

    customer_order_col = pick_column("customer_order_no")
    if customer_order_col is None:
        raise ValueError("订单管理中未找到“客户订单号”列。")

    rows: Dict[str, Dict[str, Any]] = {}
    for _, row in df.iterrows():
        customer_order_no = normalize_customer_order_no(row.get(customer_order_col, ""))
        if not customer_order_no:
            continue
        transport_no_col = pick_column("transport_no")
        job_date_col = pick_column("job_date")
        hk_plate_col = pick_column("hk_plate")
        seamless_no_col = pick_column("seamless_no")
        rows[customer_order_no] = {
            "customer_order_no": customer_order_no,
            "transport_no": normalize_identifier(row.get(transport_no_col, "")) if transport_no_col else "",
            "job_date": parse_order_date(row.get(job_date_col, "")) if job_date_col else datetime(1900, 1, 1),
            "hk_plate": extract_hk_plate(row.get(hk_plate_col, "")) if hk_plate_col else "",
            "seamless_no": normalize_identifier(row.get(seamless_no_col, "")) if seamless_no_col else "",
        }
    return rows


def parse_order_date(value: object) -> datetime:
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str) and value is not None and not pd.isna(value):
        try:
            return pd.to_datetime(value).to_pydatetime()
        except Exception:  # noqa: BLE001
            pass
    text = str(value or "").strip()
    if not text or text.lower() == "nan":
        return datetime(1900, 1, 1)
    return pd.to_datetime(text).to_pydatetime()


def extract_hk_plate(raw_value: object) -> str:
    text = str(raw_value or "").strip().upper()
    if not text or text == "NAN":
        return ""

    import re

    matches = re.findall(r"\b([A-Z]{1,2}\s?\d{3,4})\b", text)
    if matches:
        return matches[-1].replace(" ", "")

    compact = text.replace(" ", "")
    match = re.search(r"([A-Z]{1,2}\d{3,4})港", compact)
    if match:
        return match.group(1)
    return normalize_identifier(text)


def unique_preserving_order(values: Iterable[object]) -> List[str]:
    result: List[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text.lower() == "nan" or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def backfill_product_names(product_names: List[str], commodity_codes: List[str]) -> List[str]:
    result = list(product_names)
    for code in commodity_codes:
        mapped_name = PRODUCT_NAME_BY_CODE.get(code)
        if mapped_name and mapped_name not in result:
            result.append(mapped_name)
    return result


def parse_customs_source_summary(path: Path) -> CustomsSourceSummary:
    return cached_file_result(
        "customs.parse_customs_source_summary",
        path,
        lambda: _parse_customs_source_summary_uncached(path),
    )


def _parse_customs_source_summary_uncached(path: Path) -> CustomsSourceSummary:
    customer_order_no = normalize_customer_order_no(path.stem)
    excel_file, _ = load_excel_file(path)
    df = excel_file.parse(excel_file.sheet_names[0], header=None)

    header_row_idx: Optional[int] = None
    for idx in range(len(df)):
        row = [normalize_header_name(v) for v in df.iloc[idx].tolist()]
        if "item" in row and any(value == "snno." for value in row):
            header_row_idx = idx
            break

    if header_row_idx is None:
        return CustomsSourceSummary(
            customer_order_no=customer_order_no,
            total_cartons=Decimal("0.00"),
            total_pcs=Decimal("0.00"),
            total_pallets=Decimal("0.00"),
            total_gross_weight=Decimal("0.00"),
            total_amount_usd=Decimal("0.00"),
            total_amount_hkd=Decimal("0.00"),
            product_names=[],
            commodity_codes=[],
            tan_nos=[],
        )

    header_map = {
        normalize_header_name(value): idx
        for idx, value in enumerate(df.iloc[header_row_idx].tolist())
        if normalize_header_name(value)
    }

    def pick(*names: str) -> Optional[int]:
        for name in names:
            key = normalize_header_name(name)
            if key in header_map:
                return header_map[key]
        return None

    pcs_col = pick("总数量PCS", "总数量", "数量")
    cartons_col = pick("箱数", "总箱数")
    pallets_col = pick("卡板数", "板数")
    gross_col = pick("毛重KG", "毛重")
    amount_usd_col = pick("总价USD", "货值")
    product_name_col = pick("品名", "货物名称", "商品名称")
    commodity_code_col = pick("商品编码", "HS CODE")

    detail_rows: List[pd.Series] = []
    for idx in range(header_row_idx + 1, len(df)):
        row = df.iloc[idx]
        first = row.iloc[0]
        second = row.iloc[1] if len(row) > 1 else ""
        first_text = str(first).strip() if not pd.isna(first) else ""
        second_text = str(second).strip() if not pd.isna(second) else ""
        if not first_text and not second_text:
            continue
        if is_source_detail_row_for_customs(first, second_text):
            detail_rows.append(row)

    total_cartons = sum_decimal_rows(detail_rows, cartons_col)
    total_pcs = sum_decimal_rows(detail_rows, pcs_col)
    total_pallets = sum_decimal_rows(detail_rows, pallets_col)
    total_gross_weight = sum_decimal_rows(detail_rows, gross_col)
    total_amount_usd = sum_decimal_rows(detail_rows, amount_usd_col)
    total_amount_hkd = quantized(total_amount_usd * USD_TO_HKD)

    customer_order_no_from_tans, tan_records = parse_source_file(path)
    tan_nos = [item.tan_no for item in tan_records]

    product_names = (
        unique_preserving_order(row.iloc[product_name_col] for row in detail_rows)
        if product_name_col is not None
        else []
    )
    commodity_codes = (
        unique_preserving_order(row.iloc[commodity_code_col] for row in detail_rows)
        if commodity_code_col is not None
        else []
    )
    product_names = backfill_product_names(product_names, commodity_codes)

    return CustomsSourceSummary(
        customer_order_no=customer_order_no_from_tans or customer_order_no,
        total_cartons=total_cartons,
        total_pcs=total_pcs,
        total_pallets=total_pallets,
        total_gross_weight=total_gross_weight,
        total_amount_usd=total_amount_usd,
        total_amount_hkd=total_amount_hkd,
        product_names=product_names,
        commodity_codes=commodity_codes,
        tan_nos=tan_nos,
    )


def is_source_detail_row_for_customs(first_value: object, second_text: str) -> bool:
    if first_value is not None and not pd.isna(first_value):
        if isinstance(first_value, (int, float)):
            return True
        first_text = str(first_value).strip()
        if first_text.isdigit():
            return True
    return second_text.upper().startswith("SN-")


def sum_decimal_rows(rows: Sequence[pd.Series], col_idx: Optional[int]) -> Decimal:
    if col_idx is None:
        return Decimal("0.00")
    return quantized(sum((parse_decimal_value(row.iloc[col_idx]) for row in rows), Decimal("0.00")))


def calculate_declaration_fee(amount_usd: Decimal) -> Decimal:
    amount_hkd = amount_usd * USD_TO_HKD
    fee = (amount_hkd - DECLARATION_FEE_THRESHOLD) * DECLARATION_FEE_RATE + DECLARATION_FEE_BASE
    if fee > DECLARATION_FEE_MAX:
        fee = DECLARATION_FEE_MAX
    elif fee < DECLARATION_FEE_MIN:
        fee = DECLARATION_FEE_MIN
    return quantized(fee)


def build_declaration_fee_formula(excel_row: int) -> str:
    return (
        f"=IF((G{excel_row}*7.85-46000)*0.000125+16.3>216.3,216.3,"
        f"IF((G{excel_row}*7.85-46000)*0.000125+16.3<16.5,16.5,"
        f"(G{excel_row}*7.85-46000)*0.000125+16.3))"
    )


def build_customs_preview_rows(
    order_rows: Dict[str, Dict[str, Any]],
    source_paths: Sequence[Path],
) -> tuple[List[CustomsPreviewRow], List[str]]:
    previews: List[CustomsPreviewRow] = []
    errors: List[str] = []
    seen_sources: set[str] = set()

    for source_path in source_paths:
        source_key = str(source_path.resolve()).lower()
        if source_key in seen_sources:
            continue
        seen_sources.add(source_key)

        try:
            summary = parse_customs_source_summary(source_path)
            order_row = order_rows.get(summary.customer_order_no)
            if not order_row:
                errors.append(f"{source_path.name}: 订单管理中未找到客户订单号 {summary.customer_order_no}")
                continue

            warnings: List[str] = []
            if not order_row["hk_plate"]:
                warnings.append("订单管理里没有可识别的香港车牌")

            previews.append(
                CustomsPreviewRow(
                    customer_order_no=summary.customer_order_no,
                    transport_no=order_row["transport_no"],
                    ship_date=order_row["job_date"],
                    ship_date_label=format_ship_date_label(order_row["job_date"]),
                    hk_plate=order_row["hk_plate"],
                    seamless_no=order_row["seamless_no"],
                    total_cartons=summary.total_cartons,
                    total_pcs=summary.total_pcs,
                    total_pallets=summary.total_pallets,
                    total_gross_weight=summary.total_gross_weight,
                    total_amount_usd=summary.total_amount_usd,
                    total_amount_hkd=summary.total_amount_hkd,
                    product_names=summary.product_names,
                    commodity_codes=summary.commodity_codes,
                    tan_nos=summary.tan_nos,
                    declaration_fee=calculate_declaration_fee(summary.total_amount_usd),
                    warnings=warnings,
                )
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{source_path.name}: {exc}")

    previews.sort(key=lambda item: item.customer_order_no)
    for idx, preview in enumerate(previews, start=1):
        preview.declaration_fee_formula = build_declaration_fee_formula(3 + idx)
    return previews, errors


def format_ship_date_label(value: datetime) -> str:
    if not value or value.year == 1900:
        return ""
    return f"{value.month}月{value.day}日"


def export_customs_preview_xlsx(rows: Sequence[CustomsPreviewRow], output_path: Path) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "清关预览"
    headers = [
        "客户订单号",
        "主单号",
        "作业时间",
        "港车车牌",
        "无缝号",
        "总箱数",
        "总PCS数",
        "总板数",
        "总毛重",
        "总金额USD",
        "总金额HKD",
        "Declaration fees",
        "Declaration fees公式",
        "品名",
        "商品编码",
        "Tan#",
        "提醒",
    ]
    ws.append(headers)

    for row in rows:
        ws.append(
            [
                row.customer_order_no,
                row.transport_no,
                row.ship_date.strftime("%Y-%m-%d %H:%M:%S") if row.ship_date.year != 1900 else "",
                row.hk_plate,
                row.seamless_no,
                int(row.total_cartons),
                int(row.total_pcs),
                int(row.total_pallets),
                float(row.total_gross_weight),
                float(row.total_amount_usd),
                float(row.total_amount_hkd),
                float(row.declaration_fee),
                row.declaration_fee_formula,
                " / ".join(row.product_names),
                " / ".join(row.commodity_codes),
                " / ".join(row.tan_nos),
                "；".join(row.warnings or []),
            ]
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(output_path)


def export_customs_bill(
    template_path: Path,
    rows: Sequence[CustomsPreviewRow],
    output_path: Path,
) -> None:
    if not rows:
        raise ValueError("没有可回填到 bill 模板的清关数据，请先检查真实数据源文件是否匹配订单管理。")

    template_path = template_path.resolve()
    output_path = output_path.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(template_path, output_path)

    payload = [
        {
            "row_no": idx + 1,
            "ship_date": row.ship_date.strftime("%Y-%m-%d"),
            "job_ref": row.customer_order_no,
            "hk_plate": row.hk_plate,
            "cartons": int(row.total_cartons),
            "gross_weight": float(row.total_gross_weight),
            "amount_usd": float(row.total_amount_usd),
            "smooth_handling": float(SMOOTH_HANDLING_FEE),
        }
        for idx, row in enumerate(rows)
    ]

    temp_json = output_path.with_suffix(".customs.json").resolve()
    temp_ps1 = output_path.with_suffix(".customs.ps1").resolve()
    powershell = f"""
$ErrorActionPreference = 'Stop'
$template = '{str(output_path)}'
$jsonPath = '{str(temp_json)}'
$rows = Get-Content -LiteralPath $jsonPath -Raw | ConvertFrom-Json
$excel = $null
$wb = $null
$ws = $null
$closeWithSave = $false
try {{
$excel = New-Object -ComObject Excel.Application
$excel.Visible = $false
$excel.DisplayAlerts = $false
$wb = $excel.Workbooks.Open($template)
$worksheetCount = $wb.Worksheets.Count
if ($worksheetCount -lt 3) {{
    throw "bill 模板只有 $worksheetCount 个工作表，程序需要第 3 个工作表用于回填。请上传包含第 3 个账单页的模板。"
}}
$ws = $wb.Worksheets.Item(3)
$sampleRow = 7
$startRow = 4
$usedLastRow = $ws.UsedRange.Row + $ws.UsedRange.Rows.Count - 1
$sampleFormula = $ws.Cells.Item($sampleRow, 10).Formula
$existingKeys = @{{}}
$rowsToWrite = New-Object System.Collections.ArrayList
$lastDataRow = $startRow - 1

function Get-KeyPart($value) {{
    if ($null -eq $value) {{
        return ''
    }}
    if ($value -is [datetime]) {{
        return $value.ToString('yyyy-MM-dd')
    }}
    try {{
        if ($value -is [double] -or $value -is [decimal] -or $value -is [int] -or $value -is [long]) {{
            return ([double]$value).ToString('0.##')
        }}
    }} catch {{
    }}
    return [string]$value
}}

function Build-RowKey($shipDate, $jobRef, $cartons, $grossWeight, $amountUsd) {{
    $parts = @(
        (Get-KeyPart $shipDate).Trim(),
        (Get-KeyPart $jobRef).Trim(),
        (Get-KeyPart $cartons).Trim(),
        (Get-KeyPart $grossWeight).Trim(),
        (Get-KeyPart $amountUsd).Trim()
    )
    return ($parts -join '|')
}}

for ($rowIndex = $startRow; $rowIndex -le $usedLastRow; $rowIndex++) {{
    $jobRefText = [string]$ws.Cells.Item($rowIndex, 3).Text
    $udrText = [string]$ws.Cells.Item($rowIndex, 8).Text
    $rowHasData = $false
    for ($colIndex = 2; $colIndex -le 10; $colIndex++) {{
        $cellText = [string]$ws.Cells.Item($rowIndex, $colIndex).Text
        if (-not [string]::IsNullOrWhiteSpace($cellText)) {{
            $rowHasData = $true
            break
        }}
    }}
    if ($rowHasData) {{
        $lastDataRow = $rowIndex
    }}
    if (-not [string]::IsNullOrWhiteSpace($udrText)) {{
        $existingKey = Build-RowKey `
            $ws.Cells.Item($rowIndex, 2).Value2 `
            $jobRefText `
            $ws.Cells.Item($rowIndex, 5).Value2 `
            $ws.Cells.Item($rowIndex, 6).Value2 `
            $ws.Cells.Item($rowIndex, 7).Value2
        if (-not [string]::IsNullOrWhiteSpace($existingKey)) {{
            $existingKeys[$existingKey] = $true
        }}
    }}
}}

foreach ($row in @($rows)) {{
    $rowKey = Build-RowKey $row.ship_date $row.job_ref $row.cartons $row.gross_weight $row.amount_usd
    if ($existingKeys.ContainsKey($rowKey)) {{
        continue
    }}
    $existingKeys[$rowKey] = $true
    [void]$rowsToWrite.Add($row)
}}

for ($index = 0; $index -lt $rowsToWrite.Count; $index++) {{
    $row = $rowsToWrite[$index]
    $targetRow = [Math]::Max($startRow, $lastDataRow + 1 + $index)
    $ws.Range("A$sampleRow:J$sampleRow").Copy() | Out-Null
    $ws.Range("A$targetRow:J$targetRow").PasteSpecial(-4122) | Out-Null
    $ws.Cells.Item($targetRow, 1).Value2 = [int]($targetRow - $startRow + 1)
    $ws.Cells.Item($targetRow, 2).Value = [datetime]::Parse($row.ship_date)
    $ws.Cells.Item($targetRow, 3).Value = [string]$row.job_ref
    $ws.Cells.Item($targetRow, 4).Value = [string]$row.hk_plate
    $ws.Cells.Item($targetRow, 5).Value2 = [int]$row.cartons
    $ws.Cells.Item($targetRow, 6).Value2 = [double]$row.gross_weight
    $ws.Cells.Item($targetRow, 7).Value2 = [double]$row.amount_usd
    $ws.Cells.Item($targetRow, 8).Value = ''
    $ws.Cells.Item($targetRow, 9).Value2 = [double]$row.smooth_handling
    $ws.Cells.Item($targetRow, 10).Formula = $sampleFormula.Replace('G7', 'G' + $targetRow)
}}
$wb.Save()
$closeWithSave = $true
}} finally {{
    if ($null -ne $wb) {{
        try {{ $wb.Close($closeWithSave) }} catch {{ }}
    }}
    if ($null -ne $excel) {{
        try {{ $excel.Quit() }} catch {{ }}
    }}
    if ($null -ne $ws) {{
        try {{ [System.Runtime.Interopservices.Marshal]::ReleaseComObject($ws) | Out-Null }} catch {{ }}
    }}
    if ($null -ne $wb) {{
        try {{ [System.Runtime.Interopservices.Marshal]::ReleaseComObject($wb) | Out-Null }} catch {{ }}
    }}
    if ($null -ne $excel) {{
        try {{ [System.Runtime.Interopservices.Marshal]::ReleaseComObject($excel) | Out-Null }} catch {{ }}
    }}
    Remove-Item -LiteralPath $jsonPath -Force -ErrorAction SilentlyContinue
}}
"""
    try:
        temp_json.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        temp_ps1.write_text(powershell, encoding="utf-8-sig")
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(temp_ps1)],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except subprocess.CalledProcessError as exc:
        details = "\n".join(
            part.strip()
            for part in [exc.stdout or "", exc.stderr or ""]
            if part and part.strip()
        )
        if not details:
            details = f"PowerShell 退出码：{exc.returncode}"
        raise RuntimeError(f"清关 bill 模板回填失败：{details}") from exc
    finally:
        temp_json.unlink(missing_ok=True)
        temp_ps1.unlink(missing_ok=True)


def reconcile_customs(
    order_management_path: Path,
    source_paths: Sequence[Path],
    bill_template_path: Optional[Path] = None,
    preview_output_path: Optional[Path] = None,
    bill_output_path: Optional[Path] = None,
) -> CustomsOutput:
    order_rows = parse_order_management(order_management_path)
    preview_rows, errors = build_customs_preview_rows(order_rows, source_paths)

    if preview_output_path:
        export_customs_preview_xlsx(preview_rows, preview_output_path)

    if bill_template_path and bill_output_path:
        try:
            export_customs_bill(bill_template_path, preview_rows, bill_output_path)
        except Exception as exc:  # noqa: BLE001
            errors.append(str(exc))
            bill_output_path = None

    return CustomsOutput(
        preview_rows=[item.to_preview() for item in preview_rows],
        errors=errors,
        preview_export_path=preview_output_path,
        bill_output_path=bill_output_path,
    )
