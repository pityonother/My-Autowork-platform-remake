"""Minimal checker for the SIL-FUCA delivery-list API.

This script compares two equivalent qty formats against GetDeliveryList_new:
plain number, for example 20000, and comma number, for example 20,000.

It intentionally uses only Python standard library modules so it can be run on
any machine with Python installed:

    python tools/check_sil_fuca_delivery_api.py
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from typing import Any


DEFAULT_URL = "http://api.clztoud.com/QIOpenApi/GetDeliveryList_new"
DEFAULT_PO = "T33U-26040025-0002"
DEFAULT_PN = "1010300202002T01"
DEFAULT_QTY = "20000"


def comma_qty(qty: str) -> str:
    raw = qty.replace(",", "").strip()
    try:
        if "." in raw:
            value = float(raw)
            if value.is_integer():
                return f"{int(value):,}"
            return f"{value:,}"
        return f"{int(raw):,}"
    except ValueError:
        return qty


def post_json(url: str, payload: dict[str, Any], timeout: int) -> tuple[int | None, dict[str, Any] | str]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            text = response.read().decode("utf-8", errors="replace")
            try:
                return response.status, json.loads(text)
            except json.JSONDecodeError:
                return response.status, text
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(text)
        except json.JSONDecodeError:
            return exc.code, text
    except Exception as exc:  # noqa: BLE001 - this is a diagnostic script.
        return None, f"{type(exc).__name__}: {exc}"


def first_record(result: dict[str, Any] | str) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {}
    data = result.get("data")
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return data[0]
    return {}


def summarize(label: str, status: int | None, result: dict[str, Any] | str) -> dict[str, Any]:
    record = first_record(result)
    if isinstance(result, dict):
        errors = result.get("errors")
        success = result.get("success")
    else:
        errors = result
        success = None

    return {
        "case": label,
        "http_status": status,
        "success": success,
        "errors": errors,
        "po": record.get("po"),
        "product_code": record.get("product_code"),
        "delivery_quantity": record.get("delivery_quantity"),
        "delivery_list_no": record.get("delivery_list_no"),
        "mes_no": record.get("mes_no"),
        "allocation_status": record.get("allocation_status"),
    }


def print_json(title: str, value: Any) -> None:
    print(title)
    print(json.dumps(value, ensure_ascii=False, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare SIL-FUCA delivery API responses.")
    parser.add_argument("--url", default=DEFAULT_URL, help=f"API URL. Default: {DEFAULT_URL}")
    parser.add_argument("--po", default=DEFAULT_PO, help=f"PO. Default: {DEFAULT_PO}")
    parser.add_argument("--pn", default=DEFAULT_PN, help=f"PN/material code. Default: {DEFAULT_PN}")
    parser.add_argument("--qty", default=DEFAULT_QTY, help=f"Quantity without comma. Default: {DEFAULT_QTY}")
    parser.add_argument("--timeout", type=int, default=60, help="Request timeout seconds. Default: 60")
    args = parser.parse_args()

    qty_plain = args.qty
    qty_comma = comma_qty(args.qty)
    cases = [
        ("qty_plain", qty_plain),
        ("qty_comma", qty_comma),
    ]

    print("SIL-FUCA delivery API minimal comparison")
    print(f"Time: {datetime.now().isoformat(timespec='seconds')}")
    print(f"URL: {args.url}")
    print(f"PO: {args.po}")
    print(f"PN: {args.pn}")
    print(f"Qty cases: {qty_plain!r} vs {qty_comma!r}")
    print()

    summaries: list[dict[str, Any]] = []
    raw_results: dict[str, Any] = {}
    for label, qty in cases:
        payload = {"list": [{"po": args.po, "pn": args.pn, "qty": qty}]}
        started = time.perf_counter()
        status, result = post_json(args.url, payload, args.timeout)
        elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
        summary = summarize(label, status, result)
        summary["request_qty"] = qty
        summary["elapsed_ms"] = elapsed_ms
        summaries.append(summary)
        raw_results[label] = {
            "request": payload,
            "http_status": status,
            "elapsed_ms": elapsed_ms,
            "response": result,
        }

    print_json("Summary comparison:", summaries)

    mes_values = {item.get("mes_no") for item in summaries}
    if len(mes_values) > 1:
        print()
        print("NOTICE: The two responses returned different mes_no values.")
        print("This may mean the API is not a pure read-only query, or it creates/allocates MES numbers per request.")

    print()
    print_json("Raw request/response:", raw_results)
    return 0


if __name__ == "__main__":
    sys.exit(main())
