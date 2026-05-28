from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.request import urlopen

from app.distribution.errors import DownloadError, HashMismatchError


@dataclass(frozen=True)
class DownloadResult:
    path: Path
    sha256: str
    size: int


def safe_download_name(module_id: str, artifact_url: str) -> str:
    name = Path(artifact_url.split("?", 1)[0].rstrip("/")).name or f"{module_id}.zip"
    cleaned = re.sub(r"[^A-Za-z0-9_.+-]+", "_", name)
    return cleaned if cleaned.lower().endswith(".zip") else f"{cleaned}.zip"


def calculate_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_artifact(
    *,
    module_id: str,
    artifact_url: str,
    expected_sha256: str,
    downloads_dir: Path,
) -> DownloadResult:
    downloads_dir.mkdir(parents=True, exist_ok=True)
    target = downloads_dir / safe_download_name(module_id, artifact_url)
    tmp_path = target.with_suffix(target.suffix + ".part")
    try:
        with urlopen(artifact_url, timeout=60) as response:  # noqa: S310 - admin-configured release URL.
            with tmp_path.open("wb") as output:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    output.write(chunk)
    except Exception as exc:  # noqa: BLE001
        tmp_path.unlink(missing_ok=True)
        raise DownloadError("下载失败，请检查网络或 manifest 的 artifact 地址。", technical_detail=str(exc)) from exc

    actual_sha256 = calculate_sha256(tmp_path)
    normalized_expected = expected_sha256.strip().lower()
    if normalized_expected and actual_sha256 != normalized_expected:
        tmp_path.unlink(missing_ok=True)
        raise HashMismatchError("校验失败，已保留原版本。", technical_detail=f"{actual_sha256} != {normalized_expected}")

    tmp_path.replace(target)
    return DownloadResult(path=target, sha256=actual_sha256, size=target.stat().st_size)
