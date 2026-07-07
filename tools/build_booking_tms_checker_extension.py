from __future__ import annotations

import argparse
import json
import os
import shutil
import zipfile
from pathlib import Path
from urllib.parse import urlparse


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXTENSION_SOURCE_DIR = PROJECT_ROOT / "browser_extensions" / "booking_tms_checker"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "dist" / "booking_tms_checker_edge"
DEFAULT_SERVER_PORT = os.environ.get("BOOKING_TMS_CHECKER_DEFAULT_PORT", "8010").strip()


def normalize_server_base(value: str) -> str:
    server_base = value.strip().rstrip("/")
    if "://" not in server_base:
        server_base = f"https://{server_base}"
    parsed = urlparse(server_base)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("server base must be a full http(s) URL, for example https://192.168.10.205:8010")
    if parsed.params or parsed.query or parsed.fragment:
        raise ValueError("server base must not include params, query, or fragment")
    if parsed.port is None and DEFAULT_SERVER_PORT:
        hostname = parsed.hostname or parsed.netloc
        if ":" in hostname and not hostname.startswith("["):
            hostname = f"[{hostname}]"
        netloc = f"{hostname}:{DEFAULT_SERVER_PORT}"
        return parsed._replace(netloc=netloc).geturl().rstrip("/")
    return parsed.geturl().rstrip("/")


def render_config_js(server_base: str) -> str:
    return (
        "window.BookingTmsCheckerConfig = Object.freeze({\n"
        f"  defaultServerBase: {json.dumps(server_base, ensure_ascii=False)},\n"
        f"  defaultServerPort: {json.dumps(DEFAULT_SERVER_PORT, ensure_ascii=False)},\n"
        "});\n"
    )


def _assert_safe_output_dir(output_dir: Path) -> Path:
    resolved = output_dir.resolve()
    source = EXTENSION_SOURCE_DIR.resolve()
    project = PROJECT_ROOT.resolve()
    if resolved == source or source in resolved.parents:
        raise ValueError("output dir must not be inside the source extension dir")
    if resolved == project:
        raise ValueError("output dir must not be the project root")
    return resolved


def write_deployment_note(output_dir: Path, server_base: str) -> None:
    note = f"""# Booking TMS Checker Deployment

默认服务地址：

```text
{server_base}
```

同事安装：

1. 打开 Edge 的 `edge://extensions/`。
2. 打开“开发人员模式”。
3. 点击“加载解压缩的扩展”。
4. 选择本文件夹。
5. 刷新 SMOOTH TMS 页面。

验收：

1. 打开 `https://smooth.clztoud.com/Home/AdminDefault`。
2. 右下角出现“Booking 质检”浮窗。
3. 选择 `.xlsx` booking form。
4. 点击“上传并打开筛查结果”。
5. 新标签页应直接打开带筛查结果的页面。
"""
    (output_dir / "DEPLOYMENT.txt").write_text(note, encoding="utf-8")


def zip_directory(source_dir: Path, zip_path: Path) -> None:
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(source_dir.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(source_dir.parent))


def build_package(server_base: str, output_dir: Path = DEFAULT_OUTPUT_DIR) -> tuple[Path, Path]:
    normalized_server_base = normalize_server_base(server_base)
    safe_output_dir = _assert_safe_output_dir(output_dir)
    if safe_output_dir.exists():
        shutil.rmtree(safe_output_dir)
    shutil.copytree(EXTENSION_SOURCE_DIR, safe_output_dir)
    (safe_output_dir / "config.js").write_text(render_config_js(normalized_server_base), encoding="utf-8")
    write_deployment_note(safe_output_dir, normalized_server_base)
    zip_path = safe_output_dir.with_suffix(".zip")
    zip_directory(safe_output_dir, zip_path)
    return safe_output_dir, zip_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the Edge extension package for coworkers.")
    parser.add_argument(
        "--server-base",
        required=True,
        help="Booking Web service base URL, for example https://192.168.10.205:8010",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Output extension folder. Default: {DEFAULT_OUTPUT_DIR}",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir, zip_path = build_package(args.server_base, args.output_dir)
    print(f"Extension folder: {output_dir}")
    print(f"Extension zip: {zip_path}")
    print(f"Default server: {normalize_server_base(args.server_base)}")


if __name__ == "__main__":
    main()
