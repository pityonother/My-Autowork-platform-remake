from __future__ import annotations

from pathlib import Path

from PIL import Image

from app.modules.ufo_mail.cover_processor import locate_first_page_replacements
from app.modules.ufo_mail.rules import detect_ufo_no
from app.modules.ufo_mail.service import safe_ufo_output_stem
from app.modules.ufo_mail.legacy_adapter import UfoAttachment


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


def test_first_page_locator_keeps_ratio_fallback_available(tmp_path) -> None:
    image = Image.new("RGB", (2000, 3000), "white")

    replacements = locate_first_page_replacements(tmp_path / "RH2600000.tif", image)

    assert [replacement.name for replacement in replacements] == ["pod_entry_no", "pod_top_barcode_text"]
    assert replacements[0].source == "pod_entry_no_ratio_fallback"
    assert replacements[0].box == (486, 315, 890, 393)
    assert replacements[1].source == "pod_top_barcode_text_ratio_fallback"
    assert replacements[1].box == (1330, 213, 1756, 297)


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


def test_clear_output_cache_removes_children_but_keeps_outputs(monkeypatch, tmp_path) -> None:
    from app.modules.ufo_mail import service

    app_dir = tmp_path / "app"
    output_dir = app_dir / "runtime" / "outputs"
    nested_dir = output_dir / "ufo_processed"
    nested_dir.mkdir(parents=True)
    (nested_dir / "preview.png").write_bytes(b"png")
    (output_dir / "mail.eml").write_text("eml", encoding="utf-8")

    monkeypatch.setattr(service, "APP_DIR", app_dir)
    monkeypatch.setattr(service, "OUTPUT_DIR", output_dir)

    result = service.clear_output_cache()

    assert result == {"deleted_files": 1, "deleted_dirs": 1}
    assert output_dir.exists()
    assert list(output_dir.iterdir()) == []


def test_prepare_ufo_attachments_keeps_non_document_attachments(monkeypatch, tmp_path) -> None:
    from app.modules.ufo_mail import service

    attachment = UfoAttachment(path=tmp_path / "photo.jpg", filename="photo.jpg")

    result = service.prepare_ufo_attachments(
        session_id="abc123",
        saved_attachments=[attachment],
        ufo_no="",
    )

    assert result == [attachment]


def test_prepare_ufo_attachments_requires_manual_ufo_no_for_tif(tmp_path) -> None:
    from app.modules.ufo_mail import service

    attachment = UfoAttachment(path=tmp_path / "RH2603126.tif", filename="RH2603126.tif")

    try:
        service.prepare_ufo_attachments(
            session_id="abc123",
            saved_attachments=[attachment],
            ufo_no="",
        )
    except ValueError as exc:
        assert "UFO" in str(exc)
    else:
        raise AssertionError("Expected missing UFO number to fail for coverable documents")


def test_generate_mail_does_not_use_filename_as_manual_ufo_no(monkeypatch, tmp_path) -> None:
    from app.modules.ufo_mail import service

    class DummyUpload:
        filename = "UFO26052201.pdf"

    def fake_save_upload(session_id, uploaded, prefix):
        return tmp_path / uploaded.filename

    def fail_processor(**kwargs):
        raise AssertionError("cover processor should not run without a manual UFO number")

    monkeypatch.setattr(service, "OUTPUT_DIR", tmp_path / "outputs")
    monkeypatch.setattr(service, "UPLOAD_DIR", tmp_path / "uploads")
    monkeypatch.setattr(service, "save_upload", fake_save_upload)
    monkeypatch.setattr(service, "run_ufo_cover_processor", fail_processor)

    try:
        service.generate_mail(
            issue_ids=[1],
            attachments=[DummyUpload()],
            ufo_no="",
            to_email="",
            cc_email="",
            from_email="",
        )
    except ValueError as exc:
        assert "UFO" in str(exc)
    else:
        raise AssertionError("Expected coverable documents to require a manual UFO number")


def test_prepare_ufo_attachments_replaces_tif_with_processed_pdf(monkeypatch, tmp_path) -> None:
    from app.modules.ufo_mail import service

    def fake_processor(**kwargs):
        kwargs["output_pdf"].parent.mkdir(parents=True, exist_ok=True)
        kwargs["output_pdf"].write_bytes(b"%PDF-1.4\n")
        kwargs["result_json"].write_text("{}", encoding="utf-8")
        return {"review_count": 0}

    monkeypatch.setattr(service, "OUTPUT_DIR", tmp_path / "outputs")
    monkeypatch.setattr(service, "run_ufo_cover_processor", fake_processor)
    attachment = UfoAttachment(path=tmp_path / "RH2603126.tif", filename="RH2603126.tif")

    result = service.prepare_ufo_attachments(
        session_id="abc123",
        saved_attachments=[attachment],
        ufo_no="UFO26052201",
    )

    assert len(result) == 1
    assert result[0].filename == "UFO26052201.pdf"
    assert result[0].path.name == "UFO26052201.pdf"
    assert result[0].path.exists()


def test_prepare_ufo_attachments_prefers_pdf_when_pdf_and_tif_are_uploaded(monkeypatch, tmp_path) -> None:
    from app.modules.ufo_mail import service

    processed_inputs: list[Path] = []

    def fake_processor(**kwargs):
        processed_inputs.append(kwargs["input_path"])
        kwargs["output_pdf"].parent.mkdir(parents=True, exist_ok=True)
        kwargs["output_pdf"].write_bytes(b"%PDF-1.4\n")
        kwargs["result_json"].write_text("{}", encoding="utf-8")
        return {"review_count": 0, "page_count": 8}

    monkeypatch.setattr(service, "OUTPUT_DIR", tmp_path / "outputs")
    monkeypatch.setattr(service, "run_ufo_cover_processor", fake_processor)
    tif_attachment = UfoAttachment(path=tmp_path / "RH2603714.tif", filename="RH2603714.tif")
    pdf_attachment = UfoAttachment(path=tmp_path / "UFO26052201.pdf", filename="UFO26052201.pdf")
    photo_attachment = UfoAttachment(path=tmp_path / "photo.jpeg", filename="photo.jpeg")

    result = service.prepare_ufo_attachments(
        session_id="abc123",
        saved_attachments=[tif_attachment, photo_attachment, pdf_attachment],
        ufo_no="UFO26052201",
    )

    assert processed_inputs == [pdf_attachment.path]
    assert [item.filename for item in result] == ["photo.jpeg", "UFO26052201.pdf"]


def test_prepare_ufo_attachments_blocks_low_confidence_review(monkeypatch, tmp_path) -> None:
    from app.modules.ufo_mail import service

    def fake_processor(**kwargs):
        kwargs["output_pdf"].parent.mkdir(parents=True, exist_ok=True)
        kwargs["output_pdf"].write_bytes(b"%PDF-1.4\n")
        kwargs["report_csv"].write_text("page,decision\n2,review_only\n", encoding="utf-8")
        kwargs["result_json"].write_text("{}", encoding="utf-8")
        return {"review_count": 1}

    monkeypatch.setattr(service, "OUTPUT_DIR", tmp_path / "outputs")
    monkeypatch.setattr(service, "run_ufo_cover_processor", fake_processor)
    attachment = UfoAttachment(path=tmp_path / "RH2603126.tif", filename="RH2603126.tif")

    try:
        service.prepare_ufo_attachments(
            session_id="abc123",
            saved_attachments=[attachment],
            ufo_no="UFO26052201",
        )
    except ValueError as exc:
        assert isinstance(exc, service.LowConfidenceReviewRequired)
        assert exc.session_id == "abc123"
    else:
        raise AssertionError("Expected low-confidence review items to block mail generation")


def test_prepare_ufo_attachments_allows_low_confidence_after_confirmation(monkeypatch, tmp_path) -> None:
    from app.modules.ufo_mail import service

    def fake_processor(**kwargs):
        kwargs["output_pdf"].parent.mkdir(parents=True, exist_ok=True)
        kwargs["output_pdf"].write_bytes(b"%PDF-1.4\n")
        kwargs["report_csv"].write_text("page,decision\n2,review_only\n", encoding="utf-8")
        kwargs["result_json"].write_text("{}", encoding="utf-8")
        return {"review_count": 1}

    monkeypatch.setattr(service, "OUTPUT_DIR", tmp_path / "outputs")
    monkeypatch.setattr(service, "run_ufo_cover_processor", fake_processor)
    attachment = UfoAttachment(path=tmp_path / "RH2603126.pdf", filename="RH2603126.pdf")

    result = service.prepare_ufo_attachments(
        session_id="abc123",
        saved_attachments=[attachment],
        ufo_no="UFO26052201",
        allow_low_confidence=True,
    )

    assert [item.filename for item in result] == ["UFO26052201.pdf"]
    assert result[0].path.exists()


def test_generate_mail_from_saved_session_reuses_uploads_after_review_confirmation(monkeypatch, tmp_path) -> None:
    from app.modules.ufo_mail import service

    session_id = "abc123def456"
    upload_dir = tmp_path / "uploads"
    output_dir = tmp_path / "outputs"
    uploaded_pdf = upload_dir / session_id / "ufo_attachment_001_RH2603126.pdf"
    uploaded_pdf.parent.mkdir(parents=True)
    uploaded_pdf.write_bytes(b"%PDF-1.4\n")

    def fake_processor(**kwargs):
        kwargs["output_pdf"].parent.mkdir(parents=True, exist_ok=True)
        kwargs["output_pdf"].write_bytes(b"%PDF-1.4\n")
        kwargs["report_csv"].write_text("page,decision\n2,review_only\n", encoding="utf-8")
        kwargs["result_json"].write_text("{}", encoding="utf-8")
        return {"review_count": 1}

    def fake_generate_ufo_eml(input_data, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(",".join(item.filename for item in input_data.attachments), encoding="utf-8")

    monkeypatch.setattr(service, "UPLOAD_DIR", upload_dir)
    monkeypatch.setattr(service, "OUTPUT_DIR", output_dir)
    monkeypatch.setattr(service, "run_ufo_cover_processor", fake_processor)
    monkeypatch.setattr(service, "generate_ufo_eml", fake_generate_ufo_eml)
    service.save_attachment_metadata(
        session_id,
        [UfoAttachment(path=uploaded_pdf, filename="RH2603126.pdf")],
    )

    output_path = service.generate_mail_from_saved_session(
        session_id=session_id,
        issue_ids=[1],
        ufo_no="UFO26052201",
        to_email="to@example.com",
        cc_email="",
        from_email="from@example.com",
        allow_low_confidence=True,
    )

    assert output_path.name == f"UFO26052201_{session_id}.eml"
    assert output_path.read_text(encoding="utf-8") == "UFO26052201.pdf"
