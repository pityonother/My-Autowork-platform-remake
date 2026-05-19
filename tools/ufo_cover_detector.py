from __future__ import annotations

import argparse
import json
from collections import deque
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from app.shared.lazy_imports import lazy_module

fitz = lazy_module("fitz")
Image = lazy_module("PIL.Image")
ImageFilter = lazy_module("PIL.ImageFilter")


POD_FIXED_BOXES = [
    ("pod_entry_no", (0.245, 0.100, 0.420, 0.130)),
    ("pod_top_barcode", (0.675, 0.025, 0.905, 0.092)),
]


@dataclass
class DetectionBox:
    page: int
    kind: str
    x0: float
    y0: float
    x1: float
    y1: float
    score: float
    note: str

    def to_rect(self) -> fitz.Rect:
        return fitz.Rect(self.x0, self.y0, self.x1, self.y1)


def render_page_gray(page: fitz.Page, dpi: int) -> Image.Image:
    matrix = fitz.Matrix(dpi / 72, dpi / 72)
    pix = page.get_pixmap(matrix=matrix, colorspace=fitz.csGRAY, alpha=False)
    return Image.frombytes("L", (pix.width, pix.height), pix.samples)


def fixed_pod_boxes(page: fitz.Page, page_number: int) -> list[DetectionBox]:
    width = page.rect.width
    height = page.rect.height
    boxes: list[DetectionBox] = []
    for name, (x0, y0, x1, y1) in POD_FIXED_BOXES:
        boxes.append(
            DetectionBox(
                page=page_number,
                kind=name,
                x0=x0 * width,
                y0=y0 * height,
                x1=x1 * width,
                y1=y1 * height,
                score=1.0,
                note="fixed POD region",
            )
        )
    return boxes


def connected_components(mask: np.ndarray, min_pixels: int) -> list[tuple[int, int, int, int, int]]:
    height, width = mask.shape
    visited = np.zeros(mask.shape, dtype=bool)
    components: list[tuple[int, int, int, int, int]] = []
    ys, xs = np.nonzero(mask)

    for start_y, start_x in zip(ys.tolist(), xs.tolist()):
        if visited[start_y, start_x]:
            continue

        queue: deque[tuple[int, int]] = deque([(start_y, start_x)])
        visited[start_y, start_x] = True
        min_x = max_x = start_x
        min_y = max_y = start_y
        pixels = 0

        while queue:
            y, x = queue.popleft()
            pixels += 1
            if x < min_x:
                min_x = x
            elif x > max_x:
                max_x = x
            if y < min_y:
                min_y = y
            elif y > max_y:
                max_y = y

            for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                if ny < 0 or ny >= height or nx < 0 or nx >= width:
                    continue
                if visited[ny, nx] or not mask[ny, nx]:
                    continue
                visited[ny, nx] = True
                queue.append((ny, nx))

        if pixels >= min_pixels:
            components.append((min_x, min_y, max_x + 1, max_y + 1, pixels))

    return components


def dilate_mask(mask: np.ndarray, *, radius_x: int, radius_y: int) -> np.ndarray:
    result = mask.copy()
    if radius_x > 0:
        horizontal = result.copy()
        for offset in range(1, radius_x + 1):
            horizontal[:, offset:] |= mask[:, :-offset]
            horizontal[:, :-offset] |= mask[:, offset:]
        result = horizontal
    if radius_y > 0:
        vertical = result.copy()
        for offset in range(1, radius_y + 1):
            vertical[offset:, :] |= result[:-offset, :]
            vertical[:-offset, :] |= result[offset:, :]
        result = vertical
    return result


def barcode_score(dark_crop: np.ndarray) -> float:
    if dark_crop.size == 0:
        return 0.0
    height, width = dark_crop.shape
    if width <= 0 or height <= 0:
        return 0.0

    density = float(dark_crop.mean())
    vertical_density = dark_crop.mean(axis=0)
    dense_cols = vertical_density > 0.32
    dense_col_ratio = float(dense_cols.mean())
    transitions = int(np.count_nonzero(dense_cols[1:] != dense_cols[:-1])) if width > 1 else 0
    transition_score = min(transitions / 55.0, 1.0)

    aspect = width / max(height, 1)
    aspect_score = 0.0
    if 1.8 <= aspect <= 12.0:
        aspect_score = 0.18
    elif 0.7 <= aspect <= 1.4:
        aspect_score = 0.10

    return min((density / 0.28) * 0.32 + dense_col_ratio * 0.35 + transition_score * 0.35 + aspect_score, 1.0)


def barcode_components(dark: np.ndarray) -> list[tuple[int, int, int, int, int]]:
    image_height, image_width = dark.shape
    barcode_mask = dilate_mask(dark, radius_x=4, radius_y=1)
    min_pixels = max(80, int(image_width * image_height * 0.00002))
    components = connected_components(barcode_mask, min_pixels=min_pixels)
    result: list[tuple[int, int, int, int, int]] = []
    for x0, y0, x1, y1, pixels in components:
        width = x1 - x0
        height = y1 - y0
        aspect = width / max(height, 1)
        if width < image_width * 0.045 or height < image_height * 0.010:
            continue
        if width > image_width * 0.40 or height > image_height * 0.12:
            continue
        if y0 < image_height * 0.58:
            continue
        if aspect < 1.35 or aspect > 8.5:
            continue
        raw_score = barcode_score(dark[max(0, y0 - 4):min(image_height, y1 + 4), max(0, x0 - 4):min(image_width, x1 + 4)])
        if raw_score < 0.45:
            continue
        result.append((x0, y0, x1, y1, pixels))
    return result


def expand_pixel_box(
    box: tuple[int, int, int, int],
    margin: int,
    image_width: int,
    image_height: int,
) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = box
    return (
        max(0, x0 - margin),
        max(0, y0 - margin),
        min(image_width, x1 + margin),
        min(image_height, y1 + margin),
    )


def clamp_pixel_box(
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    image_width: int,
    image_height: int,
) -> tuple[int, int, int, int]:
    return (
        max(0, int(round(x0))),
        max(0, int(round(y0))),
        min(image_width, int(round(x1))),
        min(image_height, int(round(y1))),
    )


def build_label_region(
    x0: int,
    y0: int,
    x1: int,
    y1: int,
    image_width: int,
    image_height: int,
) -> tuple[int, int, int, int]:
    width = x1 - x0
    height = y1 - y0
    aspect = width / max(height, 1)
    if aspect >= 2.05:
        return clamp_pixel_box(
            x0 - height * 1.05,
            y0 - height * 0.12,
            x1 + height * 0.45,
            y1 + height * 1.45,
            image_width,
            image_height,
        )
    return clamp_pixel_box(
        x0 - width * 0.08,
        y0 - height * 0.08,
        x1 + width * 0.08,
        y1 + height * 0.16,
        image_width,
        image_height,
    )


def large_text_score(dark_crop: np.ndarray) -> float:
    if dark_crop.size == 0:
        return 0.0
    height, width = dark_crop.shape
    if height < 10 or width < 20:
        return 0.0
    lower = dark_crop[int(height * 0.48):, :]
    if lower.size == 0:
        return 0.0
    density = float(lower.mean())
    row_density = lower.mean(axis=1)
    dense_rows = float((row_density > 0.08).mean())
    col_density = lower.mean(axis=0)
    text_cols = float((col_density > 0.06).mean())
    return min((density / 0.18) * 0.45 + dense_rows * 0.30 + text_cols * 0.25, 1.0)


def label_shape_score(width: int, height: int) -> float:
    if width <= 0 or height <= 0:
        return 0.0
    aspect = width / height
    if 1.10 <= aspect <= 2.15:
        return 1.0
    if 0.85 <= aspect < 1.10:
        return 0.72
    if 2.15 < aspect <= 2.65:
        return 0.45
    return 0.0


def is_original_header_barcode(
    x0: int,
    y0: int,
    x1: int,
    y1: int,
    image_width: int,
    image_height: int,
) -> bool:
    width = x1 - x0
    height = y1 - y0
    aspect = width / max(height, 1)
    return y0 < image_height * 0.16 and width > image_width * 0.20 and aspect > 2.15


def score_label_region(dark: np.ndarray, region: tuple[int, int, int, int], raw_barcode_score: float) -> float:
    x0, y0, x1, y1 = region
    crop = dark[y0:y1, x0:x1]
    width = x1 - x0
    height = y1 - y0
    shape = label_shape_score(width, height)
    text = large_text_score(crop)
    density = float(crop.mean()) if crop.size else 0.0
    density_score = 1.0 if 0.08 <= density <= 0.38 else max(0.0, 1.0 - abs(density - 0.18) / 0.18)
    return min(raw_barcode_score * 0.42 + shape * 0.30 + text * 0.22 + density_score * 0.06, 1.0)


def margin_dark_density(dark: np.ndarray, region: tuple[int, int, int, int]) -> float:
    image_height, image_width = dark.shape
    x0, y0, x1, y1 = region
    width = x1 - x0
    height = y1 - y0
    ex0 = max(0, x0 - int(width * 0.45))
    ex1 = min(image_width, x1 + int(width * 0.45))
    ey0 = max(0, y0 - int(height * 0.45))
    ey1 = min(image_height, y1 + int(height * 0.45))
    if ex1 <= ex0 or ey1 <= ey0:
        return 1.0
    margin_mask = np.ones((ey1 - ey0, ex1 - ex0), dtype=bool)
    margin_mask[y0 - ey0:y1 - ey0, x0 - ex0:x1 - ex0] = False
    if not margin_mask.any():
        return 1.0
    return float(dark[ey0:ey1, ex0:ex1][margin_mask].mean())


def is_footer_edge_fragment(region: tuple[int, int, int, int], image_width: int, image_height: int) -> bool:
    x0, y0, x1, _ = region
    return y0 > image_height * 0.64 and (x0 < image_width * 0.09 or x1 > image_width * 0.985)


def overlap_ratio(a: DetectionBox, b: DetectionBox) -> float:
    ax0, ay0, ax1, ay1 = a.x0, a.y0, a.x1, a.y1
    bx0, by0, bx1, by1 = b.x0, b.y0, b.x1, b.y1
    ix0 = max(ax0, bx0)
    iy0 = max(ay0, by0)
    ix1 = min(ax1, bx1)
    iy1 = min(ay1, by1)
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    intersection = (ix1 - ix0) * (iy1 - iy0)
    smaller = min((ax1 - ax0) * (ay1 - ay0), (bx1 - bx0) * (by1 - by0))
    return intersection / max(smaller, 1.0)


def suppress_overlaps(boxes: list[DetectionBox]) -> list[DetectionBox]:
    selected: list[DetectionBox] = []
    for box in sorted(boxes, key=lambda item: (item.score, -((item.x1 - item.x0) * (item.y1 - item.y0))), reverse=True):
        if any(overlap_ratio(box, kept) > 0.55 for kept in selected):
            continue
        selected.append(box)
    return sorted(selected, key=lambda item: (item.page, item.y0, item.x0))


def detect_label_boxes(page: fitz.Page, page_number: int, *, dpi: int, min_score: float) -> list[DetectionBox]:
    image = render_page_gray(page, dpi)
    gray = np.asarray(image)
    image_height, image_width = gray.shape

    dark = gray < 170
    mask_image = Image.fromarray((dark.astype(np.uint8) * 255), mode="L")
    dilated = mask_image.filter(ImageFilter.MaxFilter(15))
    dilated_mask = np.asarray(dilated) > 0

    min_pixels = max(60, int(image_width * image_height * 0.00003))
    components = connected_components(dilated_mask, min_pixels=min_pixels)
    components.extend(barcode_components(dark))
    page_width = page.rect.width
    page_height = page.rect.height
    scale_x = page_width / image_width
    scale_y = page_height / image_height
    detections: list[DetectionBox] = []

    for x0, y0, x1, y1, pixels in components:
        box_width = x1 - x0
        box_height = y1 - y0
        if box_width < image_width * 0.025 or box_height < image_height * 0.008:
            continue
        if box_width > image_width * 0.48 or box_height > image_height * 0.20:
            continue
        if pixels > image_width * image_height * 0.08:
            continue
        if x0 <= 3 or y0 <= 3 or x1 >= image_width - 3 or y1 >= image_height - 3:
            continue

        if is_original_header_barcode(x0, y0, x1, y1, image_width, image_height):
            continue

        ex0, ey0, ex1, ey1 = expand_pixel_box((x0, y0, x1, y1), 6, image_width, image_height)
        crop = dark[ey0:ey1, ex0:ex1]
        raw_score = barcode_score(crop)
        if raw_score < 0.48:
            continue

        region = build_label_region(ex0, ey0, ex1, ey1, image_width, image_height)
        if is_original_header_barcode(*region, image_width, image_height):
            continue
        rx0, ry0, rx1, ry1 = region
        if is_footer_edge_fragment(region, image_width, image_height):
            continue
        margin_density = margin_dark_density(dark, region)
        if margin_density > 0.12:
            continue
        score = score_label_region(dark, region, raw_score)
        if score < min_score:
            continue

        detections.append(
            DetectionBox(
                page=page_number,
                kind="label_candidate",
                x0=rx0 * scale_x,
                y0=ry0 * scale_y,
                x1=rx1 * scale_x,
                y1=ry1 * scale_y,
                score=round(score, 3),
                note=f"RH-label-like component, raw={raw_score:.3f}, margin={margin_density:.3f}, pixels={pixels}",
            )
        )

    selected = suppress_overlaps(detections)
    return sorted(selected, key=lambda item: item.score, reverse=True)[:1]


def draw_detection_boxes(doc: fitz.Document, detections: list[DetectionBox]) -> None:
    by_page: dict[int, list[DetectionBox]] = {}
    for detection in detections:
        by_page.setdefault(detection.page, []).append(detection)

    for page_number, boxes in by_page.items():
        page = doc[page_number - 1]
        for index, detection in enumerate(boxes, start=1):
            rect = detection.to_rect()
            page.draw_rect(rect, color=(1, 0, 0), width=2.0, overlay=True)
            label = f"{index} {detection.kind} {detection.score:.2f}"
            label_point = fitz.Point(rect.x0, max(8, rect.y0 - 5))
            page.insert_text(
                label_point,
                label,
                fontsize=8,
                color=(1, 0, 0),
                overlay=True,
            )


def detect_pdf(input_pdf: Path, output_pdf: Path, *, dpi: int, min_score: float) -> list[DetectionBox]:
    doc = fitz.open(input_pdf)
    detections: list[DetectionBox] = []
    for page_index, page in enumerate(doc, start=1):
        if page_index == 1:
            detections.extend(fixed_pod_boxes(page, page_index))
        else:
            detections.extend(detect_label_boxes(page, page_index, dpi=dpi, min_score=min_score))

    draw_detection_boxes(doc, detections)
    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    doc.save(output_pdf, garbage=4, deflate=True)
    return detections


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a UFO cover detection review PDF with red boxes.")
    parser.add_argument("input_pdf", type=Path)
    parser.add_argument("output_pdf", type=Path)
    parser.add_argument("--ufo-no", default="", help="Reserved for the next cover-generation step.")
    parser.add_argument("--dpi", type=int, default=150)
    parser.add_argument("--min-score", type=float, default=0.55)
    parser.add_argument("--json-output", type=Path, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    detections = detect_pdf(args.input_pdf, args.output_pdf, dpi=args.dpi, min_score=args.min_score)
    payload = [asdict(item) for item in detections]
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output_pdf": str(args.output_pdf), "detections": payload}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
