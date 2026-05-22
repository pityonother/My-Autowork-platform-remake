from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "runtime" / "yolo_ufo_dataset_raw"
SUPPORTED_EXTENSIONS = {".pdf", ".tif", ".tiff"}


@dataclass
class ExportedPage:
    source_path: str
    source_name: str
    source_type: str
    page_number: int
    image_path: str
    image_width: int
    image_height: int
    dpi: float | list[float] | None
    is_pod_candidate: bool


def source_type_for_path(path: Path) -> str | None:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return "pdf"
    if suffix in {".tif", ".tiff"}:
        return "tiff"
    return None


def build_page_filename(source_path: Path, page_number: int) -> str:
    return f"{source_path.stem}_p{page_number:03d}.png"


def discover_input_files(paths: Iterable[Path], *, recursive: bool) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
            files.append(path)
            continue
        if path.is_dir():
            pattern = "**/*" if recursive else "*"
            files.extend(item for item in path.glob(pattern) if item.is_file() and item.suffix.lower() in SUPPORTED_EXTENSIONS)
    return sorted({item.resolve() for item in files}, key=lambda item: str(item).lower())


def normalize_dpi(value: object) -> float | list[float] | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, tuple) and value:
        cleaned = [float(item) for item in value if isinstance(item, (int, float))]
        return cleaned or None
    return None


def save_pil_image_as_png(image: object, output_path: Path) -> tuple[int, int]:
    from PIL import Image

    if not isinstance(image, Image.Image):
        raise TypeError("Expected a PIL image")

    if image.mode in {"RGBA", "LA"}:
        background = Image.new("RGB", image.size, "white")
        background.paste(image.convert("RGBA"), mask=image.convert("RGBA").split()[-1])
        image_to_save = background
    else:
        image_to_save = image.convert("RGB")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    image_to_save.save(output_path)
    return image_to_save.size


def export_tiff_pages(source_path: Path, pages_dir: Path, *, overwrite: bool) -> list[ExportedPage]:
    from PIL import Image, ImageSequence

    exported: list[ExportedPage] = []
    with Image.open(source_path) as image:
        dpi = normalize_dpi(image.info.get("dpi"))
        for page_index, frame in enumerate(ImageSequence.Iterator(image), start=1):
            output_path = pages_dir / build_page_filename(source_path, page_index)
            if output_path.exists() and not overwrite:
                raise FileExistsError(f"Output already exists: {output_path}")
            width, height = save_pil_image_as_png(frame.copy(), output_path)
            exported.append(
                ExportedPage(
                    source_path=str(source_path),
                    source_name=source_path.name,
                    source_type="tiff",
                    page_number=page_index,
                    image_path=str(output_path),
                    image_width=width,
                    image_height=height,
                    dpi=dpi,
                    is_pod_candidate=page_index == 1,
                )
            )
    return exported


def export_pdf_pages(source_path: Path, pages_dir: Path, *, dpi: int, overwrite: bool) -> list[ExportedPage]:
    import fitz

    exported: list[ExportedPage] = []
    matrix = fitz.Matrix(dpi / 72, dpi / 72)
    with fitz.open(source_path) as doc:
        for page_index, page in enumerate(doc, start=1):
            output_path = pages_dir / build_page_filename(source_path, page_index)
            if output_path.exists() and not overwrite:
                raise FileExistsError(f"Output already exists: {output_path}")
            pix = page.get_pixmap(matrix=matrix, colorspace=fitz.csRGB, alpha=False)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            pix.save(output_path)
            exported.append(
                ExportedPage(
                    source_path=str(source_path),
                    source_name=source_path.name,
                    source_type="pdf",
                    page_number=page_index,
                    image_path=str(output_path),
                    image_width=pix.width,
                    image_height=pix.height,
                    dpi=float(dpi),
                    is_pod_candidate=page_index == 1,
                )
            )
    return exported


def export_pages(
    input_paths: Iterable[Path],
    output_root: Path,
    *,
    recursive: bool,
    pdf_dpi: int,
    overwrite: bool,
) -> list[ExportedPage]:
    pages_dir = output_root / "pages"
    input_files = discover_input_files(input_paths, recursive=recursive)
    if not input_files:
        raise FileNotFoundError("No .pdf, .tif, or .tiff files found in the requested input paths.")

    exported: list[ExportedPage] = []
    seen_outputs: set[Path] = set()
    for source_path in input_files:
        source_type = source_type_for_path(source_path)
        if source_type is None:
            continue
        first_output = (pages_dir / build_page_filename(source_path, 1)).resolve()
        if first_output in seen_outputs:
            raise ValueError(f"Output filename collision for source stem: {source_path.stem}")
        seen_outputs.add(first_output)

        if source_type == "pdf":
            exported.extend(export_pdf_pages(source_path, pages_dir, dpi=pdf_dpi, overwrite=overwrite))
        else:
            exported.extend(export_tiff_pages(source_path, pages_dir, overwrite=overwrite))
    return exported


def write_manifest(exported: list[ExportedPage], output_root: Path) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    rows = [asdict(item) for item in exported]
    (output_root / "manifest.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    with (output_root / "manifest.csv").open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0].keys()) if rows else [])
        if rows:
            writer.writeheader()
            writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export UFO/RH PDF or multi-page TIFF files into page PNGs for YOLO annotation.")
    parser.add_argument("inputs", nargs="+", type=Path, help="Input files or directories. Supports .pdf, .tif, .tiff.")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--recursive", action="store_true", help="Scan input directories recursively.")
    parser.add_argument("--pdf-dpi", type=int, default=200, help="Render DPI used for PDF inputs.")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing PNG outputs.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    exported = export_pages(
        args.inputs,
        args.output_root,
        recursive=args.recursive,
        pdf_dpi=args.pdf_dpi,
        overwrite=args.overwrite,
    )
    write_manifest(exported, args.output_root)
    print(
        json.dumps(
            {
                "output_root": str(args.output_root),
                "pages_dir": str(args.output_root / "pages"),
                "exported_pages": len(exported),
                "pod_candidates": sum(1 for item in exported if item.is_pod_candidate),
                "manifest": str(args.output_root / "manifest.json"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
