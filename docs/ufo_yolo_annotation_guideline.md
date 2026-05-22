# UFO/RH YOLO Annotation Guideline

## Target

Train one detection class:

```yaml
names:
  0: rh_sticker
```

`rh_sticker` means the full manually attached RH paper label that should be covered later.

## Label This

- The whole manually attached RH label.
- The barcode, RH number text, white label background, and visible label border.
- A slightly larger box is acceptable when it helps future cover generation. Keep the margin small and consistent.
- If a page has multiple manually attached RH labels, annotate each label separately.
- If a label is cut off by the scan/page edge, annotate only the visible part.

## Do Not Label This

- POD fixed RH area on page 1.
- Native page header barcode.
- Table fields such as Reference, DN, PO, SKU, PN, amount, date, address, or signature areas.
- Warehouse stickers that are not RH labels.
- Pure table lines, stamps, black blocks, handwritten marks, or document titles.
- Pages with no RH label. Keep these pages as empty-label negative samples.

## POD Rule

Do not delete POD pages automatically during raw export. They may be useful as negative candidates or for separate template checks.

For this first YOLO model, do not annotate the POD fixed RH area as `rh_sticker`. The POD fixed area is handled by the existing template logic.

## Negative Samples

Negative samples are pages with no RH sticker target. They must have an empty YOLO `.txt` file.

Useful negative pages include:

- Content pages without external labels.
- Pages with header barcodes only.
- Pages with table barcodes or dense table lines.
- Pages with Reference, DN, PO, SKU, PN, or similar text that could confuse the detector.

Artificially covered images, if used, must be marked as `synthetic_negative=true` in the manifest and should only be placed in `train`, not `val` or `test`.

## Split Rule

Split by source file or source group. Different pages from the same TIFF/PDF must not appear across train, val, and test.

## Before Training

Training is allowed only when:

- Every positive image has a non-empty YOLO label file.
- Every negative image has an empty YOLO label file.
- `dataset_readiness.json` says `train_ready: true`.
- Real business PDF/TIFF/PNG files, labels, runs, and model weights remain outside Git.
