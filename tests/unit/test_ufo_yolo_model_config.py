from __future__ import annotations


def test_resolve_model_path_prefers_explicit_path(monkeypatch, tmp_path) -> None:
    from app.modules.ufo_mail import cover_processor

    explicit_model = tmp_path / "explicit.pt"
    packaged_model = tmp_path / "packaged.pt"
    explicit_model.write_bytes(b"explicit")
    packaged_model.write_bytes(b"packaged")

    monkeypatch.setattr(cover_processor, "PACKAGED_MODEL_PATH", packaged_model)
    monkeypatch.setattr(cover_processor, "LEGACY_RUNTIME_MODEL_PATH", tmp_path / "missing-legacy.pt")
    monkeypatch.delenv("UFO_YOLO_MODEL", raising=False)

    assert cover_processor.resolve_model_path(explicit_model) == explicit_model


def test_resolve_model_path_uses_env_override(monkeypatch, tmp_path) -> None:
    from app.modules.ufo_mail import cover_processor

    env_model = tmp_path / "env-model.pt"
    env_model.write_bytes(b"env")

    monkeypatch.setattr(cover_processor, "PACKAGED_MODEL_PATH", tmp_path / "missing-packaged.pt")
    monkeypatch.setattr(cover_processor, "LEGACY_RUNTIME_MODEL_PATH", tmp_path / "missing-legacy.pt")
    monkeypatch.setenv("UFO_YOLO_MODEL", str(env_model))

    assert cover_processor.resolve_model_path() == env_model


def test_resolve_model_path_defaults_to_packaged_model(monkeypatch, tmp_path) -> None:
    from app.modules.ufo_mail import cover_processor

    packaged_model = tmp_path / "packaged.pt"
    legacy_model = tmp_path / "legacy.pt"
    packaged_model.write_bytes(b"packaged")
    legacy_model.write_bytes(b"legacy")

    monkeypatch.setattr(cover_processor, "PACKAGED_MODEL_PATH", packaged_model)
    monkeypatch.setattr(cover_processor, "LEGACY_RUNTIME_MODEL_PATH", legacy_model)
    monkeypatch.delenv("UFO_YOLO_MODEL", raising=False)

    assert cover_processor.resolve_model_path() == packaged_model


def test_resolve_model_path_keeps_legacy_runtime_fallback(monkeypatch, tmp_path) -> None:
    from app.modules.ufo_mail import cover_processor

    legacy_model = tmp_path / "legacy.pt"
    legacy_model.write_bytes(b"legacy")

    monkeypatch.setattr(cover_processor, "PACKAGED_MODEL_PATH", tmp_path / "missing-packaged.pt")
    monkeypatch.setattr(cover_processor, "LEGACY_RUNTIME_MODEL_PATH", legacy_model)
    monkeypatch.delenv("UFO_YOLO_MODEL", raising=False)

    assert cover_processor.resolve_model_path() == legacy_model


def test_normalize_yolo_device_supports_auto_and_explicit_devices() -> None:
    from app.modules.ufo_mail.cover_processor import normalize_yolo_device

    assert normalize_yolo_device(None) == ""
    assert normalize_yolo_device("") == ""
    assert normalize_yolo_device("auto") == ""
    assert normalize_yolo_device("default") == ""
    assert normalize_yolo_device("cpu") == "cpu"
    assert normalize_yolo_device("mps") == "mps"
    assert normalize_yolo_device("0") == "0"


def test_first_page_ufo_number_uses_legible_calibrated_fonts() -> None:
    from app.modules.ufo_mail.cover_processor import FIRST_PAGE_FONT_SIZE_BY_NAME

    assert FIRST_PAGE_FONT_SIZE_BY_NAME["pod_entry_no"] >= 68
    assert FIRST_PAGE_FONT_SIZE_BY_NAME["pod_top_barcode_text"] >= 52


def test_load_font_prefers_explicit_pod_font_path(monkeypatch, tmp_path) -> None:
    from app.modules.ufo_mail import cover_processor

    font_path = tmp_path / "pod-font.ttf"
    font_path.write_bytes(b"font")
    sentinel = object()
    calls: list[tuple[str, int]] = []

    def fake_truetype(path: str, size: int):
        calls.append((path, size))
        return sentinel

    monkeypatch.setattr(cover_processor.ImageFont, "truetype", fake_truetype)
    monkeypatch.setenv("UFO_POD_FONT_PATH", str(font_path))

    assert cover_processor.load_font(64) is sentinel
    assert calls == [(str(font_path), 64)]


def test_fit_font_size_keeps_calibrated_ufo_text_inside_cover_box() -> None:
    from app.modules.ufo_mail.cover_processor import fallback_first_page_replacements, fit_font_size_to_box
    from PIL import Image

    image = Image.new("RGB", (2458, 3473), "white")
    replacements = fallback_first_page_replacements(image)

    entry = replacements["pod_entry_no"]
    barcode = replacements["pod_top_barcode_text"]

    assert fit_font_size_to_box(text="UFO26061501", box=entry.box, anchor=entry.anchor, font_size=entry.font_size) >= 60
    assert fit_font_size_to_box(text="UFO26061501", box=barcode.box, anchor=barcode.anchor, font_size=barcode.font_size) >= 48


def test_load_tiff_pages_skips_malformed_missing_dimension_frame(monkeypatch, tmp_path) -> None:
    from app.modules.ufo_mail import cover_processor
    from PIL import Image

    class FakeTiff:
        @property
        def n_frames(self) -> int:
            raise TypeError("Missing dimensions")

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def seek(self, frame_index: int) -> None:
            if frame_index == 1:
                raise TypeError("Missing dimensions")

        def convert(self, mode: str):
            assert mode == "RGB"
            return Image.new("RGB", (20, 10), "white")

    monkeypatch.setattr(cover_processor.Image, "open", lambda _path: FakeTiff())

    pages = cover_processor.load_tiff_pages(tmp_path / "broken-extra-frame.tif")

    assert len(pages) == 1
    assert pages[0].size == (20, 10)


def test_load_tiff_pages_reports_when_no_frames_are_readable(monkeypatch, tmp_path) -> None:
    import pytest

    from app.modules.ufo_mail import cover_processor

    class BrokenTiff:
        @property
        def n_frames(self) -> int:
            raise TypeError("Missing dimensions")

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def seek(self, _frame_index: int) -> None:
            raise TypeError("Missing dimensions")

        def convert(self, _mode: str):
            raise AssertionError("convert should not be called for a broken frame")

    monkeypatch.setattr(cover_processor.Image, "open", lambda _path: BrokenTiff())

    with pytest.raises(ValueError, match="No readable pages found"):
        cover_processor.load_tiff_pages(tmp_path / "fully-broken.tif")
