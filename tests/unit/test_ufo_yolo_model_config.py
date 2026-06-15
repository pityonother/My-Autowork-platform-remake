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
