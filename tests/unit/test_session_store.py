from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter
from fastapi.testclient import TestClient

from app.factory import create_app
from app.shared.state import SESSION_STORE
from app.shared.sessions import SessionStore


def test_session_store_set_get_and_cleanup() -> None:
    store = SessionStore()
    store.set("old", {"value": 1})
    store["new"] = {"value": 2}
    store._metadata["old"]["created_at"] = store._now() - timedelta(hours=25)

    assert store.get_required("new") == {"value": 2}
    assert store.cleanup(max_age_hours=24) == ["old"]
    assert "old" not in store
    assert "new" in store


def test_session_store_cleanup_if_due_skips_until_interval_elapsed() -> None:
    store = SessionStore()
    store.set("old", {"value": 1})
    store._metadata["old"]["created_at"] = store._now() - timedelta(hours=25)

    assert store.cleanup_if_due(max_age_hours=24, interval_minutes=15) == ["old"]

    store.set("older", {"value": 2})
    store._metadata["older"]["created_at"] = store._now() - timedelta(hours=25)

    assert store.cleanup_if_due(max_age_hours=24, interval_minutes=15) == []
    assert "older" in store


def test_create_app_request_triggers_session_cleanup() -> None:
    router = APIRouter()

    @router.get("/ping")
    def ping() -> dict[str, str]:
        return {"ok": "1"}

    SESSION_STORE.clear()
    SESSION_STORE._metadata.clear()
    SESSION_STORE._last_cleanup_at = SESSION_STORE._now() - timedelta(minutes=20)
    SESSION_STORE["old"] = {"value": 1}
    SESSION_STORE._metadata["old"]["created_at"] = SESSION_STORE._now() - timedelta(hours=25)

    client = TestClient(create_app("session-cleanup-test", routers=[router], init_runtime=False))
    response = client.get("/ping")

    assert response.status_code == 200
    assert "old" not in SESSION_STORE
