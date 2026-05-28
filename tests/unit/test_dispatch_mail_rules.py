from __future__ import annotations

from PIL import Image

from dispatch_mail_store import build_ticket_snapshot_rows, render_ticket_snapshot_image
from app.modules.dispatch_mail.rules.match import content_match_score, extract_match_tokens
from app.modules.dispatch_mail.rules.naming import build_dispatch_attachment_name, unique_filename


def test_extract_match_tokens_keeps_business_identifiers() -> None:
    tokens = extract_match_tokens("Customer PO ABC-12345, TAN# 98765, shipping attached")

    assert "abc12345" in tokens
    assert "98765" in tokens
    assert "shipping" not in tokens


def test_content_match_score_prefers_identifier_overlap() -> None:
    score = content_match_score("SO ABC-12345 cartons", "ticket ABC-12345 pallets")

    assert score >= 0.70


def test_dispatch_attachment_names_are_stable_and_unique() -> None:
    filename = build_dispatch_attachment_name("2板1箱", "dqth", 1, ".xlsx")
    used = {filename}

    assert filename == "2板1箱装箱单(1).xlsx"
    assert unique_filename(filename, used) == "2板1箱装箱单(1)(2).xlsx"


def test_dispatch_snapshot_rows_keep_mail_body_columns_only() -> None:
    rows = [
        ["序号", "Customer PO", "Ship Mode", "PCS", "卡板数", "箱数"],
        ["1", "42276", "by sea", "192", "2", "2"],
        ["TAN#84328"],
    ]

    snapshot_rows = build_ticket_snapshot_rows(
        rows,
        start_row=1,
        tan_row=2,
        tan_no="TAN#84328",
        remark="TAN#84328 CLUB CAR cutoff MAY.29 17:00PM",
        item_col=0,
        po_col=1,
        ship_mode_col=2,
        pcs_col=3,
        pallet_col=4,
        carton_col=5,
    )

    assert snapshot_rows == [
        ["TAN#84328", "42276", "by sea", "192", "2", "2", ""],
        ["备注", "TAN#84328 CLUB CAR cutoff MAY.29 17:00PM", "", "", "", "", ""],
    ]


def test_dispatch_snapshot_image_stays_narrow_and_wraps_note(tmp_path) -> None:
    output_path = render_ticket_snapshot_image(
        tan_no="TAN#84329",
        preview_rows=[
            ["TAN#84329", "42596", "by air", "75", "1", "75", ""],
            [
                "备注",
                "TAN#84329 Haulotte France under SO 107786 via EAS SO#160-12686096 货交大莲排道 乐馨工业中心地下 - 国汇仓 PANDA",
                "",
                "",
                "",
                "",
                "",
            ],
        ],
        output_path=tmp_path / "ticket.png",
    )

    width, height = Image.open(output_path).size
    assert width <= 700
    assert height >= 160
