from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any


DELIVERY_LIST_NEW_URL = "http://api.clztoud.com/QIOpenApi/GetDeliveryList_new"
DELIVERY_LIST_ALL_URL = "http://api.clztoud.com/QIOpenApi/GetAllDeliveryList"
DELIVERY_LIST_NEW_URL_ENV = "SIL_FUCA_DELIVERY_LIST_NEW_URL"
DELIVERY_LIST_ALL_URL_ENV = "SIL_FUCA_DELIVERY_LIST_ALL_URL"


@dataclass(frozen=True)
class SilFucaDeliveryQuery:
    po: str
    pn: str
    qty: Decimal

    def payload(self) -> dict[str, str]:
        return {
            "po": self.po,
            "pn": self.pn,
            "qty": _format_decimal(self.qty),
        }


@dataclass(frozen=True)
class SilFucaDeliveryRecord:
    po: str
    product_code: str
    delivery_quantity: Decimal | None
    delivery_date: date | None
    delivery_list_no: str = ""
    allocation_status: str = ""

    @classmethod
    def from_api(cls, payload: dict[str, Any]) -> "SilFucaDeliveryRecord":
        po = str(payload.get("po") or "").strip()
        if not po:
            po = "-".join(
                str(payload.get(part) or "").strip()
                for part in ("purchase_order_type", "purchase_order_no", "purchase_order_seq")
            ).strip("-")
        return cls(
            po=po.upper(),
            product_code=str(payload.get("product_code") or "").strip().upper(),
            delivery_quantity=_decimal(payload.get("delivery_quantity")),
            delivery_date=_date(payload.get("delivery_date")),
            delivery_list_no=str(payload.get("delivery_list_no") or "").strip(),
            allocation_status=str(payload.get("allocation_status") or "").strip(),
        )


@dataclass(frozen=True)
class SilFucaDeliveryResponse:
    success: bool
    records: tuple[SilFucaDeliveryRecord, ...] = ()
    errors: tuple[str, ...] = ()


class SilFucaDeliveryClient:
    def __init__(
        self,
        *,
        list_new_url: str | None = None,
        list_all_url: str | None = None,
        timeout_seconds: int = 20,
    ) -> None:
        self.list_new_url = list_new_url or os.environ.get(DELIVERY_LIST_NEW_URL_ENV, DELIVERY_LIST_NEW_URL)
        self.list_all_url = list_all_url or os.environ.get(DELIVERY_LIST_ALL_URL_ENV, DELIVERY_LIST_ALL_URL)
        self.timeout_seconds = timeout_seconds
        self._query_cache: dict[tuple[str, str, str], SilFucaDeliveryResponse] = {}
        self._all_records_cache: tuple[SilFucaDeliveryRecord, ...] | None = None

    def get_delivery_list_new(self, query: SilFucaDeliveryQuery) -> SilFucaDeliveryResponse:
        cache_key = (query.po, query.pn, _format_decimal(query.qty))
        if cache_key in self._query_cache:
            return self._query_cache[cache_key]

        payload = {"list": [query.payload()]}
        raw = self._post_json(self.list_new_url, payload)
        response = _delivery_response(raw)
        self._query_cache[cache_key] = response
        return response

    def get_all_delivery_list(self) -> tuple[SilFucaDeliveryRecord, ...]:
        if self._all_records_cache is None:
            raw = self._get_json(self.list_all_url)
            if not isinstance(raw, list):
                self._all_records_cache = ()
            else:
                self._all_records_cache = tuple(
                    SilFucaDeliveryRecord.from_api(item)
                    for item in raw
                    if isinstance(item, dict)
                )
        return self._all_records_cache

    def _post_json(self, url: str, payload: dict[str, Any]) -> Any:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        return self._open_json(request)

    def _get_json(self, url: str) -> Any:
        request = urllib.request.Request(url, method="GET")
        return self._open_json(request)

    def _open_json(self, request: urllib.request.Request) -> Any:
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                text = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            text = exc.read().decode("utf-8", errors="replace")
        except Exception as exc:  # noqa: BLE001 - surface network failures as validation warnings.
            raise RuntimeError(f"SIL-FUCA 周期清单接口请求失败：{exc}") from exc
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise RuntimeError("SIL-FUCA 周期清单接口返回的不是 JSON。") from exc


def _delivery_response(raw: Any) -> SilFucaDeliveryResponse:
    if not isinstance(raw, dict):
        return SilFucaDeliveryResponse(False, errors=("SIL-FUCA 周期清单接口返回格式异常。",))
    data = raw.get("data")
    records = tuple(
        SilFucaDeliveryRecord.from_api(item)
        for item in (data if isinstance(data, list) else [])
        if isinstance(item, dict)
    )
    errors = tuple(str(item) for item in raw.get("errors", ()) if item)
    return SilFucaDeliveryResponse(bool(raw.get("success")) and bool(records), records, errors)


def _decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, AttributeError):
        return None


def _format_decimal(value: Decimal) -> str:
    if value == value.to_integral_value():
        return f"{value:.0f}"
    return format(value, "f").rstrip("0").rstrip(".")


def _date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    normalized = text.replace("Z", "").replace("T", " ")
    try:
        return datetime.fromisoformat(normalized).date()
    except ValueError:
        pass
    for candidate, fmt in ((normalized[:19], "%Y-%m-%d %H:%M:%S"), (normalized[:10], "%Y-%m-%d")):
        try:
            return datetime.strptime(candidate, fmt).date()
        except ValueError:
            continue
    return None
