from __future__ import annotations

from pathlib import Path

from tools import ufo_export_training_pages
from tools import ufo_prepare_yolo_dataset


def test_export_page_helpers_support_pdf_and_multipage_tiff() -> None:
    assert ufo_export_training_pages.source_type_for_path(Path("RH260001.pdf")) == "pdf"
    assert ufo_export_training_pages.source_type_for_path(Path("RH260001.TIF")) == "tiff"
    assert ufo_export_training_pages.source_type_for_path(Path("RH260001.tiff")) == "tiff"
    assert ufo_export_training_pages.source_type_for_path(Path("RH260001.png")) is None
    assert ufo_export_training_pages.build_page_filename(Path("RH260001.tif"), 3) == "RH260001_p003.png"


def test_prepare_yolo_dataset_copies_positive_and_negative_labels(tmp_path: Path) -> None:
    split_root = tmp_path / "split"
    positive_label_root = tmp_path / "positive_labels"
    for split in ufo_prepare_yolo_dataset.SPLITS:
        positive_dir = split_root / split / "positive_with_label" / "images"
        negative_dir = split_root / split / "negative_without_label" / "images"
        negative_label_dir = split_root / split / "negative_without_label" / "labels_empty"
        positive_dir.mkdir(parents=True)
        negative_dir.mkdir(parents=True)
        negative_label_dir.mkdir(parents=True)
        (positive_dir / f"{split}_positive.png").write_bytes(b"fake png")
        (negative_dir / f"{split}_negative.png").write_bytes(b"fake png")
        (negative_label_dir / f"{split}_negative.txt").write_text("", encoding="utf-8")
        (positive_label_root / split).mkdir(parents=True, exist_ok=True)
        (positive_label_root / split / f"{split}_positive.txt").write_text("0 0.5 0.5 0.2 0.2\n", encoding="utf-8")

    output_root = tmp_path / "yolo"
    readiness = ufo_prepare_yolo_dataset.prepare_dataset(
        split_root,
        output_root,
        positive_label_root=positive_label_root,
        allow_missing_positive_labels=False,
        overwrite=False,
    )

    assert readiness["train_ready"] is True
    assert (output_root / "ufo_rh_sticker.yaml").is_file()
    assert (output_root / "images" / "train" / "train_positive.png").is_file()
    assert (output_root / "labels" / "train" / "train_positive.txt").read_text(encoding="utf-8").strip()
    assert (output_root / "labels" / "train" / "train_negative.txt").read_text(encoding="utf-8") == ""
    assert readiness["counts"]["train"]["images"] == 2
    assert readiness["counts"]["train"]["labels"] == 2
