from __future__ import annotations

from pathlib import Path

from app.modules.ufo_mail.rules import detect_ufo_no
from app.modules.ufo_mail.service import safe_ufo_output_stem


def test_detect_ufo_no_uses_first_business_identifier() -> None:
    assert detect_ufo_no(["photo.jpg", "ufo1234567 damage.png", "UFO9999999.pdf"]) == "UFO1234567"


def test_detect_ufo_no_returns_blank_without_identifier() -> None:
    assert detect_ufo_no(["photo.jpg", "report.pdf"]) == ""


def test_safe_ufo_output_stem_keeps_business_identifier() -> None:
    assert safe_ufo_output_stem("case UFO1234567 / damaged") == "UFO1234567"


def test_safe_ufo_output_stem_removes_path_separators() -> None:
    for raw_value in ["../../pwn", "..\\..\\pwn", "UFO:bad/name\r\nnext"]:
        stem = safe_ufo_output_stem(raw_value)
        assert ".." not in stem
        assert "/" not in stem
        assert "\\" not in stem
        assert ":" not in stem
        assert "\r" not in stem
        assert "\n" not in stem


def test_ufo_mail_output_path_stays_inside_output_dir(monkeypatch, tmp_path) -> None:
    from app.modules.ufo_mail import service

    def fake_generate_ufo_eml(input_data, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(input_data.ufo_no or "", encoding="utf-8")

    monkeypatch.setattr(service, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(service, "generate_ufo_eml", fake_generate_ufo_eml)

    path = service.generate_mail(
        issue_ids=[1],
        attachments=[],
        ufo_no="../../pwn",
        to_email="",
        cc_email="",
        from_email="",
    )

    assert path.resolve().is_relative_to(tmp_path.resolve())
    assert ".." not in path.name
    assert "/" not in path.name
    assert "\\" not in path.name
