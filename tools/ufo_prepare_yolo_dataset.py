from __future__ import annotations

import argparse
import csv
import json
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "runtime" / "yolo_ufo_dataset"
SPLITS = ("train", "val", "test")
POSITIVE_ROLE = "positive_with_label"
NEGATIVE_ROLE = "negative_without_label"


@dataclass
class PreparedItem:
    split: str
    role: str
    image_name: str
    source_image_path: str
    output_image_path: str
    output_label_path: str
    label_status: str


def split_image_dir(split_root: Path, split: str, role: str) -> Path:
    return split_root / split / role / "images"


def split_negative_label_dir(split_root: Path, split: str) -> Path:
    return split_root / split / NEGATIVE_ROLE / "labels_empty"


def resolve_positive_label_path(label_root: Path, split: str, image_name: str) -> Path | None:
    stem = Path(image_name).stem
    candidates = [
        label_root / split / f"{stem}.txt",
        label_root / "labels" / split / f"{stem}.txt",
        label_root / f"{stem}.txt",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def ensure_clean_output_root(output_root: Path, *, overwrite: bool) -> None:
    if output_root.exists():
        existing = list(output_root.iterdir())
        if existing and not overwrite:
            raise FileExistsError(f"Output root is not empty: {output_root}. Use --overwrite to replace it.")
        if existing and overwrite:
            for name in [
                "images",
                "labels",
                "dataset_manifest.csv",
                "dataset_manifest.json",
                "dataset_readiness.json",
                "ufo_rh_sticker.yaml",
            ]:
                child = output_root / name
                if child.is_dir():
                    shutil.rmtree(child)
                elif child.exists():
                    child.unlink()
    output_root.mkdir(parents=True, exist_ok=True)


def copy_item(src_image: Path, src_label: Path | None, output_root: Path, split: str, role: str, label_status: str) -> PreparedItem:
    out_image = output_root / "images" / split / src_image.name
    out_label = output_root / "labels" / split / f"{src_image.stem}.txt"
    out_image.parent.mkdir(parents=True, exist_ok=True)
    out_label.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src_image, out_image)
    if src_label is not None:
        shutil.copy2(src_label, out_label)
    return PreparedItem(
        split=split,
        role=role,
        image_name=src_image.name,
        source_image_path=str(src_image),
        output_image_path=str(out_image),
        output_label_path=str(out_label) if src_label is not None else "",
        label_status=label_status,
    )


def write_dataset_yaml(output_root: Path) -> None:
    yaml_text = "\n".join(
        [
            f"path: {output_root.as_posix()}",
            "train: images/train",
            "val: images/val",
            "test: images/test",
            "names:",
            "  0: rh_sticker",
            "",
        ]
    )
    (output_root / "ufo_rh_sticker.yaml").write_text(yaml_text, encoding="utf-8")


def prepare_dataset(
    split_root: Path,
    output_root: Path,
    *,
    positive_label_root: Path | None,
    allow_missing_positive_labels: bool,
    overwrite: bool,
) -> dict[str, object]:
    ensure_clean_output_root(output_root, overwrite=overwrite)

    prepared: list[PreparedItem] = []
    missing_positive_labels: list[str] = []
    empty_positive_labels: list[str] = []

    for split in SPLITS:
        positive_dir = split_image_dir(split_root, split, POSITIVE_ROLE)
        negative_dir = split_image_dir(split_root, split, NEGATIVE_ROLE)
        negative_label_dir = split_negative_label_dir(split_root, split)

        for src_image in sorted(positive_dir.glob("*.png"), key=lambda item: item.name.lower()):
            src_label = resolve_positive_label_path(positive_label_root, split, src_image.name) if positive_label_root else None
            if src_label is None:
                missing_positive_labels.append(str(src_image))
                if not allow_missing_positive_labels:
                    continue
                prepared.append(copy_item(src_image, None, output_root, split, POSITIVE_ROLE, "missing_positive_label"))
                continue
            if src_label.stat().st_size == 0:
                empty_positive_labels.append(str(src_label))
            prepared.append(copy_item(src_image, src_label, output_root, split, POSITIVE_ROLE, "positive_label_copied"))

        for src_image in sorted(negative_dir.glob("*.png"), key=lambda item: item.name.lower()):
            src_label = negative_label_dir / f"{src_image.stem}.txt"
            if not src_label.exists():
                raise FileNotFoundError(f"Missing empty negative label for {src_image}")
            prepared.append(copy_item(src_image, src_label, output_root, split, NEGATIVE_ROLE, "empty_negative_label_copied"))

    if missing_positive_labels and not allow_missing_positive_labels:
        raise FileNotFoundError(
            f"Missing {len(missing_positive_labels)} positive YOLO label files. "
            "Pass --positive-label-root or use --allow-missing-positive-labels only for annotation staging."
        )
    if empty_positive_labels:
        raise ValueError(f"Found {len(empty_positive_labels)} empty labels for positive images; check annotation export.")

    write_dataset_yaml(output_root)
    counts = {
        split: {
            "images": len(list((output_root / "images" / split).glob("*.png"))),
            "labels": len(list((output_root / "labels" / split).glob("*.txt"))),
            "missing_positive_labels": sum(
                1 for item in prepared if item.split == split and item.role == POSITIVE_ROLE and item.label_status == "missing_positive_label"
            ),
        }
        for split in SPLITS
    }
    readiness = {
        "split_root": str(split_root),
        "output_root": str(output_root),
        "train_ready": not missing_positive_labels,
        "missing_positive_label_count": len(missing_positive_labels),
        "empty_positive_label_count": len(empty_positive_labels),
        "counts": counts,
        "yaml": str(output_root / "ufo_rh_sticker.yaml"),
    }

    rows = [asdict(item) for item in prepared]
    (output_root / "dataset_manifest.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    with (output_root / "dataset_manifest.csv").open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0].keys()) if rows else [])
        if rows:
            writer.writeheader()
            writer.writerows(rows)
    (output_root / "dataset_readiness.json").write_text(json.dumps(readiness, ensure_ascii=False, indent=2), encoding="utf-8")
    return readiness


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Materialize a UFO/RH split folder into a standard Ultralytics YOLO dataset.")
    parser.add_argument("split_root", type=Path, help="Split folder with train/val/test role subfolders.")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--positive-label-root", type=Path, default=None, help="Root containing YOLO txt labels for positive images.")
    parser.add_argument(
        "--allow-missing-positive-labels",
        action="store_true",
        help="Stage images before annotation is complete. Do not train from this output until readiness says train_ready=true.",
    )
    parser.add_argument("--overwrite", action="store_true", help="Replace existing output root.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    readiness = prepare_dataset(
        args.split_root,
        args.output_root,
        positive_label_root=args.positive_label_root,
        allow_missing_positive_labels=args.allow_missing_positive_labels,
        overwrite=args.overwrite,
    )
    print(json.dumps(readiness, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
