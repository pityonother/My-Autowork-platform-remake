from __future__ import annotations

from collections.abc import Iterator, MutableMapping
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException


class SessionStore(MutableMapping[str, dict[str, Any]]):
    def __init__(self) -> None:
        self._items: dict[str, dict[str, Any]] = {}
        self._metadata: dict[str, dict[str, datetime]] = {}

    def __getitem__(self, key: str) -> dict[str, Any]:
        self._metadata.setdefault(key, self._new_metadata())["last_accessed_at"] = self._now()
        return self._items[key]

    def __setitem__(self, key: str, value: dict[str, Any]) -> None:
        self.set(key, value)

    def __delitem__(self, key: str) -> None:
        del self._items[key]
        self._metadata.pop(key, None)

    def __iter__(self) -> Iterator[str]:
        return iter(self._items)

    def __len__(self) -> int:
        return len(self._items)

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    def _new_metadata(self) -> dict[str, datetime]:
        now = self._now()
        return {"created_at": now, "last_accessed_at": now}

    def set(self, session_id: str, value: dict[str, Any]) -> None:
        self._items[session_id] = value
        metadata = self._metadata.get(session_id)
        if metadata is None:
            self._metadata[session_id] = self._new_metadata()
        else:
            metadata["last_accessed_at"] = self._now()

    def cleanup(self, max_age_hours: int = 24) -> list[str]:
        cutoff = self._now() - timedelta(hours=max_age_hours)
        expired = [
            session_id
            for session_id, metadata in self._metadata.items()
            if metadata["created_at"] < cutoff
        ]
        for session_id in expired:
            self._items.pop(session_id, None)
            self._metadata.pop(session_id, None)
        return expired

    def get_required(self, session_id: str, detail: str = "未找到这次导入记录。") -> dict[str, Any]:
        if session_id not in self._items or not self._items[session_id]:
            raise HTTPException(status_code=404, detail=detail)
        return self[session_id]


def get_required_session(
    store: SessionStore,
    session_id: str,
    detail: str = "未找到这次导入记录。",
) -> dict[str, Any]:
    return store.get_required(session_id, detail)
