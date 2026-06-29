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

    assert "/modules/booking/body-validation/extension-upload" in content_script
    assert 'target="_blank"' in content_script
    assert 'class="booking-tms-open" type="submit" disabled' in content_script
    assert "form.addEventListener('submit'" in content_script
    assert "window.open(`${serverBase}/modules/booking/body-validation`" not in content_script
    assert "escapeHtml" in content_script
    assert popup_html.index("config.js") < popup_html.index("popup.js")


def test_booking_tms_extension_build_package_injects_server_base(tmp_path) -> None:
    output_dir = tmp_path / "booking_tms_checker_edge"

    package_dir, zip_path = build_package("http://192.168.1.20:8042/", output_dir=output_dir)

    assert package_dir == output_dir.resolve()
    assert zip_path.is_file()
    assert 'defaultServerBase: "http://192.168.1.20:8042"' in (package_dir / "config.js").read_text(
        encoding="utf-8"
    )
    assert "http://192.168.1.20:8042" in (package_dir / "DEPLOYMENT.txt").read_text(encoding="utf-8")
    with zipfile.ZipFile(zip_path) as archive:
        names = set(archive.namelist())
    assert "booking_tms_checker_edge/manifest.json" in names
    assert "booking_tms_checker_edge/config.js" in names
    assert "booking_tms_checker_edge/content.js" in names


def test_booking_tms_extension_rejects_invalid_server_base() -> None:
    for value in ["", "127.0.0.1:8042", "ftp://192.168.1.20", "http://host:8042?x=1"]:
        try:
            normalize_server_base(value)
        except ValueError:
            continue
        raise AssertionError(f"expected invalid server base: {value}")
