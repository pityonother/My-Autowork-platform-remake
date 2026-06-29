from __future__ import annotations

import asyncio
import contextlib
import json
import os
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from app.core.paths import RUNTIME_DIR


DELIVERY_LIST_NEW_URL = "http://api.clztoud.com/QIOpenApi/GetDeliveryList_new"
DELIVERY_LIST_ALL_URL = "http://api.clztoud.com/QIOpenApi/GetAllDeliveryList"
DELIVERY_LIST_NEW_URL_ENV = "SIL_FUCA_DELIVERY_LIST_NEW_URL"
DELIVERY_LIST_ALL_URL_ENV = "SIL_FUCA_DELIVERY_LIST_ALL_URL"
DELIVERY_LIST_CACHE_SECONDS_ENV = "SIL_FUCA_DELIVERY_LIST_CACHE_SECONDS"
DELIVERY_LIST_CACHE_FILE_ENV = "SIL_FUCA_DELIVERY_LIST_CACHE_FILE"
DELIVERY_LIST_LOCK_STALE_SECONDS_ENV = "SIL_FUCA_DELIVERY_LIST_LOCK_STALE_SECONDS"
DELIVERY_LIST_AUTO_REFRESH_ENV = "SIL_FUCA_DELIVERY_LIST_AUTO_REFRESH"
DELIVERY_LIST_REFRESH_INTERVAL_SECONDS_ENV = "SIL_FUCA_DELIVERY_LIST_REFRESH_INTERVAL_SECONDS"
DELIVERY_LIST_REFRESH_START_DELAY_SECONDS_ENV = "SIL_FUCA_DELIVERY_LIST_REFRESH_START_DELAY_SECONDS"
DEFAULT_DELIVERY_LIST_CACHE_SECONDS = 30 * 60
DEFAULT_DELIVERY_LIST_LOCK_STALE_SECONDS = 5 * 60
DEFAULT_DELIVERY_LIST_REFRESH_START_DELAY_SECONDS = 60
DEFAULT_DELIVERY_LIST_CACHE_PATH = RUNTIME_DIR / "booking_delivery_cache" / "sil_fuca_all_delivery_list.json"


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


@dataclass(frozen=True)
class SilFucaDeliveryCacheStatus:
    state: str
    record_count: int = 0
    updated_at: datetime | None = None
    max_age_seconds: int = DEFAULT_DELIVERY_LIST_CACHE_SECONDS
    error: str = ""

    @property
    def is_loaded(self) -> bool:
        return self.updated_at is not None and self.record_count > 0

    @property
    def is_stale(self) -> bool:
        if self.updated_at is None:
            return False
        return (datetime.now() - self.updated_at).total_seconds() > self.max_age_seconds

    @property
    def updated_at_text(self) -> str:
        return self.updated_at.strftime("%H:%M") if self.updated_at else ""

    @property
    def label(self) -> str:
        if self.state == "missing":
            return "周期清单 未加载"
        if self.state == "refreshing" and self.is_loaded:
            return f"周期清单刷新中，当前使用 {self.updated_at_text} 的旧数据 · {self.record_count} 条"
        if self.state == "refreshing":
            return "周期清单刷新中"
        if self.state == "error" and self.is_loaded:
            return f"周期清单刷新失败，当前使用 {self.updated_at_text} 的旧数据 · {self.record_count} 条"
        if self.state == "error":
            return "周期清单刷新失败"
        if self.is_stale:
            return f"周期清单 可能已过期 · 上次更新 {self.updated_at_text} · {self.record_count} 条"
        return f"周期清单 已更新 {self.updated_at_text} · {self.record_count} 条"


@dataclass
class _AllDeliveryListCache:
    records: tuple[SilFucaDeliveryRecord, ...] = ()
    updated_at: datetime | None = None
    error: str = ""


_ALL_DELIVERY_LIST_CACHE = _AllDeliveryListCache()
_BACKGROUND_REFRESH_TASK: asyncio.Task[None] | None = None


class SilFucaDeliveryClient:
    def __init__(
        self,
        *,
        list_new_url: str | None = None,
        list_all_url: str | None = None,
        timeout_seconds: int = 20,
        cache_max_age_seconds: int | None = None,
        force_refresh_all: bool = False,
    ) -> None:
        self.list_new_url = list_new_url or os.environ.get(DELIVERY_LIST_NEW_URL_ENV, DELIVERY_LIST_NEW_URL)
        self.list_all_url = list_all_url or os.environ.get(DELIVERY_LIST_ALL_URL_ENV, DELIVERY_LIST_ALL_URL)
        self.timeout_seconds = timeout_seconds
        self.cache_max_age_seconds = cache_max_age_seconds or _cache_seconds()
        self.force_refresh_all = force_refresh_all
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

    def get_all_delivery_list(self, *, force_refresh: bool = False) -> tuple[SilFucaDeliveryRecord, ...]:
        effective_force_refresh = force_refresh or self.force_refresh_all
        _sync_shared_cache_from_disk()
        if (
            self._all_records_cache is None
            or effective_force_refresh
            or _shared_cache_is_stale(self.cache_max_age_seconds)
        ):
            if not effective_force_refresh and _shared_cache_usable(self.cache_max_age_seconds):
                self._all_records_cache = _ALL_DELIVERY_LIST_CACHE.records
                return self._all_records_cache
            lock_path = _acquire_refresh_lock()
            if lock_path is None:
                _sync_shared_cache_from_disk()
                if _ALL_DELIVERY_LIST_CACHE.records:
                    self._all_records_cache = _ALL_DELIVERY_LIST_CACHE.records
                    self.force_refresh_all = False
                    return self._all_records_cache
                raise RuntimeError("SIL-FUCA 周期清单正在刷新，请稍后再试。")
            try:
                _sync_shared_cache_from_disk()
                if not effective_force_refresh and _shared_cache_usable(self.cache_max_age_seconds):
                    self._all_records_cache = _ALL_DELIVERY_LIST_CACHE.records
                    self.force_refresh_all = False
                    return self._all_records_cache
                raw = self._get_json(self.list_all_url)
            except Exception as exc:
                _ALL_DELIVERY_LIST_CACHE.error = str(exc)
                _write_persistent_cache(
                    _ALL_DELIVERY_LIST_CACHE.records,
                    updated_at=_ALL_DELIVERY_LIST_CACHE.updated_at,
                    error=_ALL_DELIVERY_LIST_CACHE.error,
                )
                if _ALL_DELIVERY_LIST_CACHE.records:
                    self._all_records_cache = _ALL_DELIVERY_LIST_CACHE.records
                    self.force_refresh_all = False
                    return self._all_records_cache
                raise
            finally:
                _release_refresh_lock(lock_path)
            records = _records_from_all_delivery_payload(raw)
            updated_at = datetime.now()
            _ALL_DELIVERY_LIST_CACHE.records = records
            _ALL_DELIVERY_LIST_CACHE.updated_at = updated_at
            _ALL_DELIVERY_LIST_CACHE.error = ""
            _write_persistent_cache(records, updated_at=updated_at, error="")
            self._all_records_cache = records
            self.force_refresh_all = False
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


def get_all_delivery_list_cache_status() -> SilFucaDeliveryCacheStatus:
    _sync_shared_cache_from_disk()
    if _refresh_lock_is_active():
        return SilFucaDeliveryCacheStatus(
            "refreshing",
            record_count=len(_ALL_DELIVERY_LIST_CACHE.records),
            updated_at=_ALL_DELIVERY_LIST_CACHE.updated_at,
            max_age_seconds=_cache_seconds(),
            error=_ALL_DELIVERY_LIST_CACHE.error,
        )
    if _ALL_DELIVERY_LIST_CACHE.error:
        return SilFucaDeliveryCacheStatus(
            "error",
            record_count=len(_ALL_DELIVERY_LIST_CACHE.records),
            updated_at=_ALL_DELIVERY_LIST_CACHE.updated_at,
            max_age_seconds=_cache_seconds(),
            error=_ALL_DELIVERY_LIST_CACHE.error,
        )
    if _ALL_DELIVERY_LIST_CACHE.updated_at is None:
        return SilFucaDeliveryCacheStatus("missing", max_age_seconds=_cache_seconds())
    return SilFucaDeliveryCacheStatus(
        "ready",
        record_count=len(_ALL_DELIVERY_LIST_CACHE.records),
        updated_at=_ALL_DELIVERY_LIST_CACHE.updated_at,
        max_age_seconds=_cache_seconds(),
    )


def refresh_all_delivery_list_if_needed(
    *,
    force: bool = False,
    client_factory: Callable[[], SilFucaDeliveryClient] | None = None,
) -> bool:
    _sync_shared_cache_from_disk()
    if not force and _shared_cache_usable(_cache_seconds()):
        return False
    if _refresh_lock_is_active():
        return False
    client = client_factory() if client_factory else SilFucaDeliveryClient()
    client.get_all_delivery_list(force_refresh=True)
    return True


def start_delivery_list_background_refresh() -> None:
    global _BACKGROUND_REFRESH_TASK
    if not _auto_refresh_enabled():
        return
    if _BACKGROUND_REFRESH_TASK is not None and not _BACKGROUND_REFRESH_TASK.done():
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    _BACKGROUND_REFRESH_TASK = loop.create_task(_delivery_list_background_refresh_loop())


async def stop_delivery_list_background_refresh() -> None:
    global _BACKGROUND_REFRESH_TASK
    task = _BACKGROUND_REFRESH_TASK
    if task is None:
        return
    _BACKGROUND_REFRESH_TASK = None
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


async def _delivery_list_background_refresh_loop() -> None:
    start_delay = _auto_refresh_start_delay_seconds()
    if start_delay:
        await asyncio.sleep(start_delay)
    while True:
        try:
            await asyncio.to_thread(refresh_all_delivery_list_if_needed)
        except Exception as exc:  # noqa: BLE001 - background refresh should not stop the app.
            _ALL_DELIVERY_LIST_CACHE.error = str(exc)
            _write_persistent_cache(
                _ALL_DELIVERY_LIST_CACHE.records,
                updated_at=_ALL_DELIVERY_LIST_CACHE.updated_at,
                error=_ALL_DELIVERY_LIST_CACHE.error,
            )
        await asyncio.sleep(_auto_refresh_interval_seconds())


def _cache_seconds() -> int:
    raw = os.environ.get(DELIVERY_LIST_CACHE_SECONDS_ENV, "").strip()
    if raw:
        try:
            return max(1, int(raw))
        except ValueError:
            pass
    return DEFAULT_DELIVERY_LIST_CACHE_SECONDS


def _auto_refresh_enabled() -> bool:
    raw = os.environ.get(DELIVERY_LIST_AUTO_REFRESH_ENV, "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def _auto_refresh_interval_seconds() -> int:
    raw = os.environ.get(DELIVERY_LIST_REFRESH_INTERVAL_SECONDS_ENV, "").strip()
    if raw:
        try:
            return max(60, int(raw))
        except ValueError:
            pass
    return _cache_seconds()


def _auto_refresh_start_delay_seconds() -> int:
    raw = os.environ.get(DELIVERY_LIST_REFRESH_START_DELAY_SECONDS_ENV, "").strip()
    if raw:
        try:
            return max(0, int(raw))
        except ValueError:
            pass
    return DEFAULT_DELIVERY_LIST_REFRESH_START_DELAY_SECONDS


def _cache_file_path() -> Path:
    raw = os.environ.get(DELIVERY_LIST_CACHE_FILE_ENV, "").strip()
    return Path(raw) if raw else DEFAULT_DELIVERY_LIST_CACHE_PATH


def _cache_lock_path() -> Path:
    cache_path = _cache_file_path()
    return cache_path.with_suffix(cache_path.suffix + ".lock")


def _lock_stale_seconds() -> int:
    raw = os.environ.get(DELIVERY_LIST_LOCK_STALE_SECONDS_ENV, "").strip()
    if raw:
        try:
            return max(1, int(raw))
        except ValueError:
            pass
    return DEFAULT_DELIVERY_LIST_LOCK_STALE_SECONDS


def _sync_shared_cache_from_disk() -> None:
    disk_cache = _read_persistent_cache()
    if disk_cache is None:
        return
    current = _ALL_DELIVERY_LIST_CACHE.updated_at
    incoming = disk_cache.updated_at
    if (
        current is None
        or (incoming is not None and incoming >= current)
        or (_ALL_DELIVERY_LIST_CACHE.error != disk_cache.error)
    ):
        _ALL_DELIVERY_LIST_CACHE.records = disk_cache.records
        _ALL_DELIVERY_LIST_CACHE.updated_at = disk_cache.updated_at
        _ALL_DELIVERY_LIST_CACHE.error = disk_cache.error


def _read_persistent_cache() -> _AllDeliveryListCache | None:
    cache_path = _cache_file_path()
    if not cache_path.is_file():
        return None
    try:
        raw = json.loads(cache_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        if not _ALL_DELIVERY_LIST_CACHE.records:
            _ALL_DELIVERY_LIST_CACHE.error = f"周期清单缓存文件读取失败：{exc}"
        return None
    if not isinstance(raw, dict):
        return None
    updated_at = _datetime(raw.get("updated_at"))
    records = tuple(
        _record_from_cache_payload(item)
        for item in (raw.get("records") if isinstance(raw.get("records"), list) else [])
        if isinstance(item, dict)
    )
    return _AllDeliveryListCache(
        records=records,
        updated_at=updated_at,
        error=str(raw.get("error") or "").strip(),
    )


def _write_persistent_cache(
    records: tuple[SilFucaDeliveryRecord, ...],
    *,
    updated_at: datetime | None,
    error: str,
) -> None:
    cache_path = _cache_file_path()
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated_at": updated_at.isoformat(timespec="seconds") if updated_at else "",
        "error": error,
        "records": [_record_to_cache_payload(record) for record in records],
    }
    temp_path = cache_path.with_suffix(cache_path.suffix + ".tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    temp_path.replace(cache_path)


def _acquire_refresh_lock() -> Path | None:
    lock_path = _cache_lock_path()
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        if not _refresh_lock_is_active():
            try:
                lock_path.unlink()
            except FileNotFoundError:
                pass
            except OSError:
                return None
            return _acquire_refresh_lock()
        return None
    payload = {
        "pid": os.getpid(),
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False))
    return lock_path


def _release_refresh_lock(lock_path: Path | None) -> None:
    if lock_path is None:
        return
    try:
        lock_path.unlink()
    except FileNotFoundError:
        pass


def _refresh_lock_is_active() -> bool:
    lock_path = _cache_lock_path()
    if not lock_path.exists():
        return False
    try:
        age = datetime.now().timestamp() - lock_path.stat().st_mtime
    except OSError:
        return True
    return age <= _lock_stale_seconds()


def _shared_cache_usable(max_age_seconds: int) -> bool:
    return bool(_ALL_DELIVERY_LIST_CACHE.records) and not _shared_cache_is_stale(max_age_seconds)


def _shared_cache_is_stale(max_age_seconds: int) -> bool:
    if _ALL_DELIVERY_LIST_CACHE.updated_at is None:
        return True
    return (datetime.now() - _ALL_DELIVERY_LIST_CACHE.updated_at).total_seconds() > max_age_seconds


def _records_from_all_delivery_payload(raw: Any) -> tuple[SilFucaDeliveryRecord, ...]:
    if not isinstance(raw, list):
        return ()
    return tuple(
        SilFucaDeliveryRecord.from_api(item)
        for item in raw
        if isinstance(item, dict)
    )


def _record_to_cache_payload(record: SilFucaDeliveryRecord) -> dict[str, str]:
    return {
        "po": record.po,
        "product_code": record.product_code,
        "delivery_quantity": _format_decimal(record.delivery_quantity) if record.delivery_quantity is not None else "",
        "delivery_date": record.delivery_date.isoformat() if record.delivery_date else "",
        "delivery_list_no": record.delivery_list_no,
        "allocation_status": record.allocation_status,
    }


def _record_from_cache_payload(payload: dict[str, Any]) -> SilFucaDeliveryRecord:
    return SilFucaDeliveryRecord(
        po=str(payload.get("po") or "").strip().upper(),
        product_code=str(payload.get("product_code") or "").strip().upper(),
        delivery_quantity=_decimal(payload.get("delivery_quantity")),
        delivery_date=_date(payload.get("delivery_date")),
        delivery_list_no=str(payload.get("delivery_list_no") or "").strip(),
        allocation_status=str(payload.get("allocation_status") or "").strip(),
    )


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


def _datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None
