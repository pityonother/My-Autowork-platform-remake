from __future__ import annotations

import json
import zipfile
from pathlib import Path

from tools.build_booking_tms_checker_extension import build_package, normalize_server_base


EXTENSION_DIR = Path(__file__).resolve().parents[2] / "browser_extensions" / "booking_tms_checker"


def test_booking_tms_extension_manifest_is_limited_to_tms_page() -> None:
    manifest = json.loads((EXTENSION_DIR / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["manifest_version"] == 3
    assert manifest["permissions"] == ["storage"]
    matches = manifest["content_scripts"][0]["matches"]
    assert "http://www.clztoud.com:8008/SupplierInquiry/*" in matches
    assert "https://smooth.clztoud.com/Home/*" in matches
    assert manifest["content_scripts"][0]["js"][:2] == ["config.js", "content.js"]
    assert "<all_urls>" not in json.dumps(manifest)
    assert "http://*/*" not in json.dumps(manifest)
    assert "https://*/*" not in json.dumps(manifest)


def test_booking_tms_extension_submits_to_extension_upload_route() -> None:
    content_script = (EXTENSION_DIR / "content.js").read_text(encoding="utf-8")
    popup_html = (EXTENSION_DIR / "popup.html").read_text(encoding="utf-8")
    popup_js = (EXTENSION_DIR / "popup.js").read_text(encoding="utf-8")

    assert "/modules/booking/body-validation/extension-upload" in content_script
    assert "fetch(buildUploadUrl(serverBase)" in content_script
    assert "x-my-autowork-token" in content_script
    assert "credentials: 'include'" in content_script
    assert "access_token" not in content_script
    assert 'class="booking-tms-open" type="submit" disabled' in content_script
    assert "form.addEventListener('submit'" in content_script
    assert "window.open(`${serverBase}/modules/booking/body-validation`" not in content_script
    assert "escapeHtml" in content_script
    assert popup_html.index("config.js") < popup_html.index("popup.js")
    assert "bookingAccessToken" in content_script
    assert "bookingAccessToken" in popup_js
    assert 'id="access-token"' in popup_html


def test_booking_tms_extension_restores_overlay_after_tms_dom_repaint_without_polling() -> None:
    content_script = (EXTENSION_DIR / "content.js").read_text(encoding="utf-8")

    assert "function ensureHost()" in content_script
    assert "new MutationObserver" in content_script
    assert "removedNodes" in content_script
    assert "observer.observe(document, { childList: true, subtree: true })" in content_script
    assert "const RESTORE_DELAY_MS = 250" in content_script
    assert "window.setTimeout" in content_script
    assert "queueMicrotask" not in content_script
    assert "renderPromise" in content_script
    assert "host.classList.toggle('is-collapsed')" in content_script
    assert "host.remove()" not in content_script
    assert "setInterval(" not in content_script


def test_booking_tms_extension_reads_defaults_from_single_config_source() -> None:
    config_js = (EXTENSION_DIR / "config.js").read_text(encoding="utf-8")
    content_js = (EXTENSION_DIR / "content.js").read_text(encoding="utf-8")
    popup_js = (EXTENSION_DIR / "popup.js").read_text(encoding="utf-8")

    assert "window.BookingTmsCheckerConfig" in config_js
    assert "defaultServerBase" in config_js
    assert "defaultServerPort" in config_js
    assert "window.BookingTmsCheckerConfig" in content_js
    assert "window.BookingTmsCheckerConfig" in popup_js
    assert "192.168.10." not in content_js
    assert "192.168.10." not in popup_js


def test_booking_tms_extension_normalizes_missing_scheme_and_port() -> None:
    assert normalize_server_base("192.168.10.205") == "https://192.168.10.205:8010"
    assert normalize_server_base("https://192.168.10.205") == "https://192.168.10.205:8010"
    assert normalize_server_base("https://192.168.10.205:9443") == "https://192.168.10.205:9443"
    assert normalize_server_base("https://192.168.10.205:443") == "https://192.168.10.205:443"


def test_booking_tms_extension_build_package_injects_server_base(tmp_path) -> None:
    output_dir = tmp_path / "booking_tms_checker_edge"

    package_dir, zip_path = build_package("https://192.168.10.205/", output_dir=output_dir)

    assert package_dir == output_dir.resolve()
    assert zip_path.is_file()
    assert 'defaultServerBase: "https://192.168.10.205:8010"' in (package_dir / "config.js").read_text(
        encoding="utf-8"
    )
    assert 'defaultServerPort: "8010"' in (package_dir / "config.js").read_text(encoding="utf-8")
    deployment_note = (package_dir / "DEPLOYMENT.txt").read_text(encoding="utf-8")
    assert "https://192.168.10.205:8010" in deployment_note
    assert "保持“已启用”" in deployment_note
    assert "代码无法绕过 Edge 的停用" in deployment_note
    assert "不要移动、重命名或删除" in deployment_note
    assert "重启电脑" in deployment_note
    assert "重新打开 Edge" in deployment_note
    with zipfile.ZipFile(zip_path) as archive:
        names = set(archive.namelist())
    assert "booking_tms_checker_edge/manifest.json" in names
    assert "booking_tms_checker_edge/config.js" in names
    assert "booking_tms_checker_edge/content.js" in names


def test_booking_tms_extension_docs_explain_unpacked_restart_boundary() -> None:
    readme = (EXTENSION_DIR / "README.md").read_text(encoding="utf-8")
    deployment = (EXTENSION_DIR / "DEPLOYMENT.md").read_text(encoding="utf-8")

    for document in (readme, deployment):
        assert "加载解压缩的扩展" in document
        assert "保持“已启用”" in document
        assert "代码无法绕过 Edge 的停用" in document
        assert "不要移动、重命名或删除" in document
        assert "重启电脑" in document
        assert "重新打开 Edge" in document


def test_booking_tms_extension_rejects_invalid_server_base() -> None:
    for value in ["", "ftp://192.168.1.20", "http://host:8010?x=1"]:
        try:
            normalize_server_base(value)
        except ValueError:
            continue
        raise AssertionError(f"expected invalid server base: {value}")
