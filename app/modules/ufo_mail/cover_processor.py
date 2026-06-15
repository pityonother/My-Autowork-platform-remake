from __future__ import annotations

import argparse
import csv
import importlib
import json
import os
import re
import statistics
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from app.core.paths import APP_DIR
from app.shared.lazy_imports import lazy_module


fitz = lazy_module("fitz")
Image = lazy_module("PIL.Image")
ImageDraw = lazy_module("PIL.ImageDraw")
ImageFont = lazy_module("PIL.ImageFont")
ImageSequence = lazy_module("PIL.ImageSequence")


SUPPORTED_DOCUMENT_SUFFIXES = {".pdf", ".tif", ".tiff"}
PACKAGED_MODEL_PATH = APP_DIR / "app" / "modules" / "ufo_mail" / "models" / "ufo_rh_sticker_final_20260521.pt"
LEGACY_RUNTIME_MODEL_PATH = APP_DIR / "runtime" / "yolo_runs" / "ufo_rh_sticker_final_20260521" / "weights" / "best.pt"
DEFAULT_MODEL_PATH = PACKAGED_MODEL_PATH
AUTO_DEVICE_VALUES = {"", "auto", "default"}
AUTO_CONFIDENCE = 0.70
REVIEW_CONFIDENCE = 0.50
BOX_PAD_RATIO = 0.08


FIRST_PAGE_REPLACEMENTS = [
    {
        "name": "pod_entry_no",
        "cover": (0.243, 0.105, 0.445, 0.131),
        "text_anchor": (0.250, 0.105),
        "font_size": 43,
    },
    {
        "name": "pod_top_barcode_text",
        "cover": (0.665, 0.071, 0.878, 0.099),
        "text_anchor": (0.695, 0.072),
        "font_size": 39,
    },
]

RH_CODE_PATTERN = re.compile(r"\bRH\s*\d{6,}\b", re.IGNORECASE)


@dataclass
class CoverReportRow:
    page: int
    source: str
    box_index: int
    conf: str
    decision: str
    x1: int
    y1: int
    x2: int
    y2: int
    fill_rgb: str = ""


@dataclass
class CoverProcessResult:
    input_path: str
    output_pdf: str
    report_json: str
    report_csv: str
    preview_dir: str
    page_count: int
    auto_cover_count: int
    review_count: int


@dataclass
class FirstPageReplacement:
    name: str
    box: tuple[int, int, int, int]
    anchor: tuple[int, int]
    font_size: int
    source: str


def is_supported_ufo_document(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_DOCUMENT_SUFFIXES


def resolve_model_path(model_path: Path | None = None) -> Path:
    candidates: list[Path] = []
    if model_path is not None:
        candidates.append(model_path)

    env_model = os.environ.get("UFO_YOLO_MODEL", "").strip()
    if env_model:
        candidates.append(Path(env_model).expanduser())

    candidates.extend([PACKAGED_MODEL_PATH, LEGACY_RUNTIME_MODEL_PATH])
    checked: list[Path] = []
    for candidate in candidates:
        resolved = candidate if candidate.is_absolute() else APP_DIR / candidate
        checked.append(resolved)
        if resolved.exists():
            return resolved

    checked_text = "; ".join(str(path) for path in checked)
    raise FileNotFoundError(f"YOLO model not found. Checked: {checked_text}")


def normalize_yolo_device(device: str | None) -> str:
    value = str(device or "").strip()
    if value.lower() in AUTO_DEVICE_VALUES:
        return ""
    return value


def load_font(size: int) -> Any:
    for font_path in [
        r"C:\Windows\Fonts\times.ttf",
        r"C:\Windows\Fonts\arial.ttf",
    ]:
        if Path(font_path).exists():
            return ImageFont.truetype(font_path, size=size)
    return ImageFont.load_default()


def clamp_box(box: tuple[float, float, float, float], width: int, height: int) -> tuple[int, int, int, int]:
    x1, y1, x2, y2 = box
    return (
        max(0, min(width - 1, int(round(x1)))),
        max(0, min(height - 1, int(round(y1)))),
        max(1, min(width, int(round(x2)))),
        max(1, min(height, int(round(y2)))),
    )


def expand_box(
    box: tuple[float, float, float, float],
    width: int,
    height: int,
    ratio: float = BOX_PAD_RATIO,
) -> tuple[int, int, int, int]:
    x1, y1, x2, y2 = box
    box_width = x2 - x1
    box_height = y2 - y1
    pad_x = max(8, box_width * ratio)
    pad_y = max(8, box_height * ratio)
    return clamp_box((x1 - pad_x, y1 - pad_y, x2 + pad_x, y2 + pad_y), width, height)


def merge_boxes(boxes: list[tuple[float, float, float, float]], gap: int = 18) -> list[tuple[float, float, float, float]]:
    pending = [tuple(map(float, box)) for box in boxes]
    changed = True
    while changed:
        changed = False
        merged: list[tuple[float, float, float, float]] = []
        used = [False] * len(pending)
        for index, current in enumerate(pending):
            if used[index]:
                continue
            cur = list(current)
            used[index] = True
            for other_index in range(index + 1, len(pending)):
                if used[other_index]:
                    continue
                x1, y1, x2, y2 = pending[other_index]
                separated = x1 > cur[2] + gap or cur[0] > x2 + gap or y1 > cur[3] + gap or cur[1] > y2 + gap
                if separated:
                    continue
                cur = [min(cur[0], x1), min(cur[1], y1), max(cur[2], x2), max(cur[3], y2)]
                used[other_index] = True
                changed = True
            merged.append(tuple(cur))
        pending = merged
    return pending


def sample_background(image: Any, box: tuple[int, int, int, int]) -> tuple[int, int, int]:
    width, height = image.size
    x1, y1, x2, y2 = box
    pad = max(18, int(max(x2 - x1, y2 - y1) * 0.12))
    rx1, ry1, rx2, ry2 = clamp_box((x1 - pad, y1 - pad, x2 + pad, y2 + pad), width, height)
    pixels: list[tuple[int, int, int]] = []
    image_pixels = image.load()
    step = max(1, int(max(rx2 - rx1, ry2 - ry1) / 120))
    for y in range(ry1, ry2, step):
        for x in range(rx1, rx2, step):
            if x1 <= x <= x2 and y1 <= y <= y2:
                continue
            r, g, b = image_pixels[x, y]
            if r + g + b >= 510:
                pixels.append((r, g, b))
    if not pixels:
        return (255, 255, 255)
    return tuple(int(statistics.median(channel)) for channel in zip(*pixels))


def cover_region(image: Any, box: tuple[int, int, int, int], fill: tuple[int, int, int] | None = None) -> tuple[int, int, int]:
    x1, y1, x2, y2 = clamp_box(tuple(float(value) for value in box), *image.size)
    fill = fill or sample_background(image, (x1, y1, x2, y2))
    draw = ImageDraw.Draw(image)
    draw.rectangle((x1, y1, x2, y2), fill=fill)
    return fill


def draw_ufo_text(image: Any, box: tuple[int, int, int, int], anchor: tuple[int, int], ufo_no: str, font_size: int) -> None:
    draw = ImageDraw.Draw(image)
    draw.text(anchor, ufo_no, fill=(0, 0, 0), font=load_font(font_size))


def fallback_first_page_replacements(image: Any) -> dict[str, FirstPageReplacement]:
    width, height = image.size
    replacements = {}
    for replacement in FIRST_PAGE_REPLACEMENTS:
        nx1, ny1, nx2, ny2 = replacement["cover"]
        ax, ay = replacement["text_anchor"]
        box = clamp_box((nx1 * width, ny1 * height, nx2 * width, ny2 * height), width, height)
        anchor = (int(round(ax * width)), int(round(ay * height)))
        name = str(replacement["name"])
        replacements[name] = FirstPageReplacement(
            name=name,
            box=box,
            anchor=anchor,
            font_size=int(replacement["font_size"]),
            source=f"{name}_ratio_fallback",
        )
    return replacements


def pdf_text_first_page_replacements(input_path: Path, image: Any) -> dict[str, FirstPageReplacement]:
    if input_path.suffix.lower() != ".pdf":
        return {}
    document = fitz.open(str(input_path))
    try:
        if document.page_count < 1:
            return {}
        page = document.load_page(0)
        words = page.get_text("words")
        if not words:
            return {}
        width, height = image.size
        scale_x = width / float(page.rect.width)
        scale_y = height / float(page.rect.height)
        candidates = []
        for word in words:
            x1, y1, x2, y2, text = word[:5]
            if not RH_CODE_PATTERN.search(str(text).replace(" ", "")):
                continue
            candidates.append((float(x1), float(y1), float(x2), float(y2), str(text)))
        replacements: dict[str, FirstPageReplacement] = {}
        for x1, y1, x2, y2, _text in candidates:
            center_x = (x1 + x2) / 2 / float(page.rect.width)
            center_y = (y1 + y2) / 2 / float(page.rect.height)
            if center_y > 0.18:
                continue
            name = "pod_top_barcode_text" if center_x > 0.55 else "pod_entry_no"
            if name in replacements:
                continue
            px1, py1 = x1 * scale_x, y1 * scale_y
            px2, py2 = x2 * scale_x, y2 * scale_y
            pad_x = max(18, (px2 - px1) * 0.18)
            pad_y = max(10, (py2 - py1) * 0.35)
            box = clamp_box((px1 - pad_x, py1 - pad_y, px2 + pad_x, py2 + pad_y), width, height)
            anchor = (max(0, int(round(px1 - pad_x * 0.35))), max(0, int(round(py1 - pad_y * 0.2))))
            font_size = int(max(24, min(52, (box[3] - box[1]) * 0.58)))
            replacements[name] = FirstPageReplacement(
                name=name,
                box=box,
                anchor=anchor,
                font_size=font_size,
                source=f"{name}_pdf_text",
            )
        return replacements
    finally:
        document.close()


def image_anchor_first_page_replacements(image: Any) -> dict[str, FirstPageReplacement]:
    try:
        import cv2
        import numpy as np
    except Exception:
        return {}

    width, height = image.size
    grayscale = np.array(image.convert("L"))
    dark_mask = (grayscale < 150).astype("uint8") * 255
    replacements: dict[str, FirstPageReplacement] = {}

    # Locate the QR-like square at the left of the POD inbound-number line.
    left_roi = dark_mask[: int(height * 0.20), : int(width * 0.24)]
    qr_mask = cv2.dilate(left_roi, cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)), iterations=1)
    count, _labels, stats, _centroids = cv2.connectedComponentsWithStats(qr_mask, 8)
    qr_candidates = []
    for index in range(1, count):
        x, y, box_width, box_height, area = stats[index]
        if area < 900:
            continue
        aspect = box_width / max(1, box_height)
        if not 0.70 <= aspect <= 1.30:
            continue
        if not (0.025 * width <= box_width <= 0.080 * width):
            continue
        if not (0.070 * height <= y <= 0.160 * height):
            continue
        qr_candidates.append((area, int(x), int(y), int(box_width), int(box_height)))
    if qr_candidates:
        _area, x, y, box_width, box_height = max(qr_candidates)
        x2 = x + box_width
        text_component_box = None
        search_x1 = max(0, int(x2 + 1.30 * box_width))
        search_x2 = min(width, int(x2 + 7.20 * box_width))
        search_y1 = max(0, int(y - 0.35 * box_height))
        search_y2 = min(height, int(y + 0.55 * box_height))
        if search_x2 > search_x1 and search_y2 > search_y1:
            entry_roi = dark_mask[search_y1:search_y2, search_x1:search_x2]
            entry_mask = cv2.dilate(entry_roi, cv2.getStructuringElement(cv2.MORPH_RECT, (35, 5)), iterations=1)
            entry_count, _entry_labels, entry_stats, _entry_centroids = cv2.connectedComponentsWithStats(entry_mask, 8)
            entry_candidates = []
            for entry_index in range(1, entry_count):
                ex, ey, ew, eh, earea = entry_stats[entry_index]
                if earea < 1200:
                    continue
                if eh < 0.010 * height or eh > 0.030 * height:
                    continue
                if ew < 0.080 * width:
                    continue
                entry_candidates.append((earea, search_x1 + int(ex), search_y1 + int(ey), int(ew), int(eh)))
            if entry_candidates:
                _earea, ex, ey, ew, eh = max(entry_candidates)
                text_component_box = (ex, ey, ex + ew, ey + eh)

        target_box = clamp_box(
            (
                (text_component_box[0] - 20) if text_component_box else x2 + 3.05 * box_width,
                (text_component_box[1] - 12) if text_component_box else y - 0.06 * box_height,
                (text_component_box[2] + 130) if text_component_box else x2 + 7.80 * box_width,
                (text_component_box[3] + 42) if text_component_box else y + 0.85 * box_height,
            ),
            width,
            height,
        )
        replacements["pod_entry_no"] = FirstPageReplacement(
            name="pod_entry_no",
            box=target_box,
            anchor=(
                max(0, int(round((text_component_box[0] - 5) if text_component_box else x2 + 3.20 * box_width))),
                max(0, int(round((text_component_box[1] + 12) if text_component_box else y - 0.04 * box_height))),
            ),
            font_size=int(max(28, min(52, (text_component_box[3] - text_component_box[1]) * 0.80 if text_component_box else box_height * 0.43))),
            source="pod_entry_no_image_anchor",
        )

    # Locate the top-right one-dimensional barcode, then replace only its RH text line.
    top_right_roi = dark_mask[: int(height * 0.085), int(width * 0.60) :]
    bar_count, _bar_labels, bar_stats, _bar_centroids = cv2.connectedComponentsWithStats(top_right_roi, 8)
    bar_candidates = []
    x_offset = int(width * 0.60)
    for index in range(1, bar_count):
        x, y, box_width, box_height, area = bar_stats[index]
        if area < 180:
            continue
        if box_height < 0.025 * height:
            continue
        if box_height > 0.045 * height:
            continue
        if y > 0.050 * height or y + box_height > 0.080 * height:
            continue
        if box_width > 0.025 * width:
            continue
        if box_height / max(1, box_width) < 2.0:
            continue
        bar_candidates.append((x + x_offset, int(y), int(box_width), int(box_height)))
    if len(bar_candidates) >= 6:
        x1 = min(x for x, _y, _w, _h in bar_candidates)
        y1 = min(y for _x, y, _w, _h in bar_candidates)
        x2 = max(x + box_width for x, _y, box_width, _h in bar_candidates)
        y2 = max(y + box_height for _x, y, _w, box_height in bar_candidates)
        barcode_width = x2 - x1
        barcode_height = y2 - y1
        target_box = clamp_box(
            (
                x1 - 0.14 * barcode_width,
                y2 + 0.01 * barcode_height,
                x2 + 0.11 * barcode_width,
                y2 + 1.02 * barcode_height,
            ),
            width,
            height,
        )
        replacements["pod_top_barcode_text"] = FirstPageReplacement(
            name="pod_top_barcode_text",
            box=target_box,
            anchor=(
                max(0, int(round(x1 + 0.04 * barcode_width))),
                max(0, int(round(y2 + 0.20 * barcode_height))),
            ),
            font_size=int(max(28, min(48, barcode_height * 0.34))),
            source="pod_top_barcode_text_image_anchor",
        )

    return replacements


def locate_first_page_replacements(input_path: Path, image: Any) -> list[FirstPageReplacement]:
    fallback = fallback_first_page_replacements(image)
    located = {}
    located.update(pdf_text_first_page_replacements(input_path, image))
    for name, replacement in image_anchor_first_page_replacements(image).items():
        located.setdefault(name, replacement)
    return [located.get(name, fallback[name]) for name in [str(item["name"]) for item in FIRST_PAGE_REPLACEMENTS]]


def cover_first_page(image: Any, ufo_no: str, input_path: Path) -> list[CoverReportRow]:
    rows: list[CoverReportRow] = []
    for index, replacement in enumerate(locate_first_page_replacements(input_path, image), start=1):
        box = replacement.box
        anchor = replacement.anchor
        fill = cover_region(image, box, fill=(255, 255, 255))
        draw_ufo_text(image, box, anchor, ufo_no, replacement.font_size)
        rows.append(
            CoverReportRow(
                page=1,
                source=replacement.source,
                box_index=index,
                conf="",
                decision="covered_with_ufo_number",
                x1=box[0],
                y1=box[1],
                x2=box[2],
                y2=box[3],
                fill_rgb=str(fill),
            )
        )
    return rows


def load_pdf_pages(path: Path, dpi: int) -> list[Any]:
    document = fitz.open(str(path))
    try:
        matrix = fitz.Matrix(dpi / 72, dpi / 72)
        pages = []
        for page in document:
            pixmap = page.get_pixmap(matrix=matrix, alpha=False)
            pages.append(Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples))
        return pages
    finally:
        document.close()


def load_tiff_pages(path: Path) -> list[Any]:
    pages = []
    with Image.open(path) as image:
        for frame in ImageSequence.Iterator(image):
            pages.append(frame.convert("RGB"))
    return pages


def load_document_pages(path: Path, dpi: int) -> list[Any]:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return load_pdf_pages(path, dpi)
    if suffix in {".tif", ".tiff"}:
        return load_tiff_pages(path)
    raise ValueError(f"Unsupported UFO document type: {path.suffix}")


def detect_yolo_boxes(
    image: Any,
    *,
    model: Any,
    page_number: int,
    auto_confidence: float,
    review_confidence: float,
    device: str,
) -> tuple[list[CoverReportRow], int, int]:
    kwargs: dict[str, Any] = {
        "imgsz": 1024,
        "conf": review_confidence,
        "verbose": False,
    }
    normalized_device = normalize_yolo_device(device)
    if normalized_device:
        kwargs["device"] = normalized_device
    result = model.predict(image, **kwargs)[0]
    detections = []
    rows: list[CoverReportRow] = []
    for raw_index, box in enumerate(result.boxes, start=1):
        confidence = float(box.conf[0].item())
        xyxy = tuple(float(value) for value in box.xyxy[0].tolist())
        decision = "auto_cover" if confidence >= auto_confidence else "review_only"
        detections.append((raw_index, confidence, xyxy, decision))
        rows.append(
            CoverReportRow(
                page=page_number,
                source="yolo_raw",
                box_index=raw_index,
                conf=f"{confidence:.4f}",
                decision=decision,
                x1=int(xyxy[0]),
                y1=int(xyxy[1]),
                x2=int(xyxy[2]),
                y2=int(xyxy[3]),
            )
        )

    auto_boxes = [xyxy for _, confidence, xyxy, _ in detections if confidence >= auto_confidence]
    merged_boxes = merge_boxes([expand_box(box, *image.size) for box in auto_boxes])
    for cover_index, merged_box in enumerate(merged_boxes, start=1):
        int_box = clamp_box(tuple(float(value) for value in merged_box), *image.size)
        fill = cover_region(image, int_box)
        rows.insert(
            0,
            CoverReportRow(
                page=page_number,
                source="yolo_merged_auto",
                box_index=cover_index,
                conf="merged",
                decision="covered",
                x1=int_box[0],
                y1=int_box[1],
                x2=int_box[2],
                y2=int_box[3],
                fill_rgb=str(fill),
            ),
        )
    review_count = sum(1 for _, confidence, _, _ in detections if review_confidence <= confidence < auto_confidence)
    return rows, len(merged_boxes), review_count


def write_report(rows: list[CoverReportRow], report_json: Path, report_csv: Path) -> None:
    report_json.parent.mkdir(parents=True, exist_ok=True)
    payload = [asdict(row) for row in rows]
    report_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    with report_csv.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=list(payload[0].keys()) if payload else list(CoverReportRow.__annotations__))
        writer.writeheader()
        writer.writerows(payload)


def save_pdf(images: list[Any], output_pdf: Path, dpi: int) -> None:
    if not images:
        raise ValueError("No pages found in the UFO document.")
    importlib.import_module("PIL.JpegImagePlugin")
    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    pdf_images = [image.convert("RGB") for image in images]
    pdf_images[0].save(output_pdf, save_all=True, append_images=pdf_images[1:], resolution=float(dpi))


def process_ufo_document(
    *,
    input_path: Path,
    output_pdf: Path,
    ufo_no: str,
    report_json: Path,
    report_csv: Path,
    preview_dir: Path,
    model_path: Path | None = None,
    dpi: int = 300,
    auto_confidence: float = AUTO_CONFIDENCE,
    review_confidence: float = REVIEW_CONFIDENCE,
    device: str = "",
) -> CoverProcessResult:
    ufo_no = ufo_no.strip().upper()
    if not ufo_no:
        raise ValueError("UFO number is required.")
    if not input_path.exists():
        raise FileNotFoundError(input_path)
    resolved_model_path = resolve_model_path(model_path)

    pages = load_document_pages(input_path, dpi=dpi)
    if not pages:
        raise ValueError("No pages found in the UFO document.")

    from ultralytics import YOLO

    model = YOLO(str(resolved_model_path))
    report_rows: list[CoverReportRow] = []
    auto_cover_count = 0
    review_count = 0
    preview_dir.mkdir(parents=True, exist_ok=True)

    report_rows.extend(cover_first_page(pages[0], ufo_no, input_path))
    for page_number, page_image in enumerate(pages[1:], start=2):
        rows, page_auto_count, page_review_count = detect_yolo_boxes(
            page_image,
            model=model,
            page_number=page_number,
            auto_confidence=auto_confidence,
            review_confidence=review_confidence,
            device=device,
        )
        report_rows.extend(rows)
        auto_cover_count += page_auto_count
        review_count += page_review_count

    for page_number, page_image in enumerate(pages, start=1):
        page_image.save(preview_dir / f"{output_pdf.stem}_p{page_number:03d}.png")

    save_pdf(pages, output_pdf, dpi=dpi)
    write_report(report_rows, report_json, report_csv)
    return CoverProcessResult(
        input_path=str(input_path),
        output_pdf=str(output_pdf),
        report_json=str(report_json),
        report_csv=str(report_csv),
        preview_dir=str(preview_dir),
        page_count=len(pages),
        auto_cover_count=auto_cover_count,
        review_count=review_count,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert an RH TIF/PDF into a covered UFO PDF.")
    parser.add_argument("input_path", type=Path)
    parser.add_argument("output_pdf", type=Path)
    parser.add_argument("--ufo-no", required=True)
    parser.add_argument("--model", type=Path, default=None)
    parser.add_argument("--report-json", type=Path, required=True)
    parser.add_argument("--report-csv", type=Path, required=True)
    parser.add_argument("--preview-dir", type=Path, required=True)
    parser.add_argument("--result-json", type=Path, required=True)
    parser.add_argument("--dpi", type=int, default=300)
    parser.add_argument("--auto-confidence", type=float, default=AUTO_CONFIDENCE)
    parser.add_argument("--review-confidence", type=float, default=REVIEW_CONFIDENCE)
    parser.add_argument("--device", default=os.environ.get("UFO_YOLO_DEVICE", "auto"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = process_ufo_document(
        input_path=args.input_path,
        output_pdf=args.output_pdf,
        ufo_no=args.ufo_no,
        report_json=args.report_json,
        report_csv=args.report_csv,
        preview_dir=args.preview_dir,
        model_path=args.model,
        dpi=args.dpi,
        auto_confidence=args.auto_confidence,
        review_confidence=args.review_confidence,
        device=args.device,
    )
    args.result_json.parent.mkdir(parents=True, exist_ok=True)
    args.result_json.write_text(json.dumps(asdict(result), ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(asdict(result), ensure_ascii=False))


if __name__ == "__main__":
    main()
