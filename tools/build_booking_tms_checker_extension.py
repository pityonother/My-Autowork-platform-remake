from __future__ import annotations

import argparse
import ipaddress
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
    had_scheme = "://" in server_base
    if not had_scheme:
        server_base = f"https://{server_base}"
    parsed = urlparse(server_base)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(
            "server base must be a full http(s) URL, "
            "for example https://booking.tools.home.arpa"
        )
    if parsed.params or parsed.query or parsed.fragment:
        raise ValueError("server base must not include params, query, or fragment")
    hostname = parsed.hostname or ""
    try:
        is_legacy_host = hostname.lower() == "localhost" or bool(
            ipaddress.ip_address(hostname)
        )
    except ValueError:
        is_legacy_host = hostname.lower() == "localhost"
    if (
        not had_scheme
        and parsed.port is None
        and DEFAULT_SERVER_PORT
        and is_legacy_host
    ):
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

重要边界：

- 这是加载解压缩的扩展，必须在 `edge://extensions/` 中保持“已启用”。
- 如果 Edge 或公司的浏览器策略将它停用，代码无法绕过 Edge 的停用，也不会修改 Windows 注册表或 Edge 策略。
- 被停用时需要手动重新启用，或由 IT 另行部署受管扩展。
- Edge 会记住本文件夹的绝对路径；安装后不要移动、重命名或删除本文件夹，更新时覆盖原目录并点击“重新加载”。
- 旧版用户的服务地址保存在 chrome.storage.local；更新后请点击插件图标，将地址改为 {server_base} 并保存一次。

验收：

1. 打开 `https://smooth.clztoud.com/Home/AdminDefault`。
2. 右下角出现“Booking 质检”浮窗。
3. 选择 `.xlsx` booking form。
4. 点击“上传并打开筛查结果”。
5. 新标签页应直接打开带筛查结果的页面。

重启验收：

1. 重启电脑，或完全退出所有 Edge 窗口后重新打开 Edge。
2. 打开 `edge://extensions/`，确认插件仍保持“已启用”，且没有加载错误。
3. 重新打开 SMOOTH TMS，确认浮窗默认展开。
4. 在 TMS 内切换页面或触发 SPA/DOM 重绘，确认浮窗被移除后会自动恢复，且不会重复出现。
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
        help="Booking Web service base URL, for example https://booking.tools.home.arpa",
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
