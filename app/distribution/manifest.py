from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse
from urllib.request import urlopen

from app.distribution.errors import ManifestError


SUPPORTED_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class ModuleManifest:
    module_id: str
    title: str
    version: str
    artifact: str
    artifact_url: str
    sha256: str
    size: int
    entry_exe: str
    landing_path: str
    start_port: int


@dataclass(frozen=True)
class ReleaseManifest:
    schema_version: int
    generated_at: str
    release_version: str
    modules: dict[str, ModuleManifest]
    source_url: str


def normalize_url(value: str) -> str:
    text = value.strip()
    if not text:
        raise ManifestError("找不到 manifest_url，请先配置更新地址。")
    parsed = urlparse(text)
    if parsed.scheme:
        return text
    return Path(text).expanduser().resolve().as_uri()


def read_manifest_json(manifest_url: str) -> dict[str, Any]:
    normalized = normalize_url(manifest_url)
    try:
        with urlopen(normalized, timeout=30) as response:  # noqa: S310 - local admin-configured URL.
            raw = response.read()
    except Exception as exc:  # noqa: BLE001
        raise ManifestError("找不到 manifest，或更新地址无法访问。", technical_detail=str(exc)) from exc
    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except Exception as exc:  # noqa: BLE001
        raise ManifestError("manifest 不是有效的 JSON 文件。", technical_detail=str(exc)) from exc
    if not isinstance(data, dict):
        raise ManifestError("manifest 顶层必须是 JSON 对象。")
    return data


def resolve_artifact_url(manifest_url: str, artifact: str) -> str:
    parsed = urlparse(artifact)
    if parsed.scheme in {"http", "https", "file"}:
        return artifact
    return urljoin(normalize_url(manifest_url), artifact)


def parse_manifest(data: dict[str, Any], *, manifest_url: str) -> ReleaseManifest:
    schema_version = data.get("schema_version")
    if schema_version != SUPPORTED_SCHEMA_VERSION:
        raise ManifestError(f"manifest schema_version 必须是 {SUPPORTED_SCHEMA_VERSION}。")
    modules_raw = data.get("modules")
    if not isinstance(modules_raw, dict):
        raise ManifestError("manifest 缺少 modules 字段。")

    modules: dict[str, ModuleManifest] = {}
    for module_id, raw in modules_raw.items():
        if not isinstance(module_id, str) or not isinstance(raw, dict):
            raise ManifestError("manifest modules 字段格式不正确。")
        required = ["title", "version", "artifact", "sha256", "size", "entry_exe", "landing_path", "start_port"]
        missing = [key for key in required if key not in raw]
        if missing:
            raise ManifestError(f"{module_id} 缺少字段：{', '.join(missing)}。")
        artifact = str(raw["artifact"])
        modules[module_id] = ModuleManifest(
            module_id=module_id,
            title=str(raw["title"]),
            version=str(raw["version"]),
            artifact=artifact,
            artifact_url=resolve_artifact_url(manifest_url, artifact),
            sha256=str(raw["sha256"]).lower(),
            size=int(raw["size"]),
            entry_exe=str(raw["entry_exe"]).replace("\\", "/"),
            landing_path=str(raw["landing_path"]),
            start_port=int(raw["start_port"]),
        )

    return ReleaseManifest(
        schema_version=schema_version,
        generated_at=str(data.get("generated_at", "")),
        release_version=str(data.get("release_version", "")),
        modules=modules,
        source_url=normalize_url(manifest_url),
    )


def load_manifest(manifest_url: str) -> ReleaseManifest:
    return parse_manifest(read_manifest_json(manifest_url), manifest_url=manifest_url)
