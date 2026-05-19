from __future__ import annotations

from pathlib import Path
from typing import Any

from app.shared.performance import cached_file_result, file_sha256


def test_file_sha256_changes_with_file_content(tmp_path: Path) -> None:
    path = tmp_path / "sample.txt"
    path.write_text("alpha", encoding="utf-8")
    first = file_sha256(path)

    path.write_text("beta", encoding="utf-8")

    assert file_sha256(path) != first


def test_cached_file_result_uses_file_hash_and_returns_copy(tmp_path: Path) -> None:
    path = tmp_path / "sample.txt"
    path.write_text("alpha", encoding="utf-8")
    calls = 0

    def loader() -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return {"items": [calls]}

    namespace = f"test.performance.{tmp_path.name}"
    first = cached_file_result(namespace, path, loader)
    first["items"].append("mutated")
    second = cached_file_result(namespace, path, loader)

    assert calls == 1
    assert second == {"items": [1]}

    path.write_text("beta", encoding="utf-8")
    third = cached_file_result(namespace, path, loader)

    assert calls == 2
    assert third == {"items": [2]}
