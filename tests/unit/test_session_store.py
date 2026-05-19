from __future__ import annotations

from datetime import timedelta

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
