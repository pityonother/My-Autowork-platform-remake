from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from dispatch_mail_store import (
    DispatchAttachment,
    DispatchDqth,
    DispatchParseResult,
    DispatchSo,
    DispatchTicket,
    build_ticket_snapshot_rows,
    match_flex_rtx_dqths,
    render_ticket_snapshot_image,
    resolve_assignments,
    ticket_dqths,
)
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
        ["SO#160-12686096"],
        ["TAN#84328"],
    ]

    snapshot_rows = build_ticket_snapshot_rows(
        rows,
        start_row=1,
        tan_row=3,
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
    assert ["TAN#84328", "", "", "", "", "", ""] not in snapshot_rows


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


def make_flex_ticket(index: int, pos: list[str], cartons: str, pallets: str, gross: str):
    return SimpleNamespace(
        index=index,
        tan_no=f"TAN#{index}",
        customer_pos=pos,
        cartons=Decimal(cartons),
        pallets=Decimal(pallets),
        gross_weight=Decimal(gross),
        include_in_dispatch=True,
        dqth=None,
        dqths=[],
    )


def make_flex_pl(pos: list[str], cartons: str, pallets: str, gross: str):
    return SimpleNamespace(
        customer_pos=pos,
        cartons=Decimal(cartons),
        pallets=Decimal(pallets),
        gross_weight=Decimal(gross),
        matched_ticket_index=None,
        status="未匹配",
    )


def make_dispatch_attachment(tmp_path: Path, name: str) -> DispatchAttachment:
    path = tmp_path / name
    path.write_text("sample", encoding="utf-8")
    return DispatchAttachment(original_name=name, stored_path=path, content_type="application/octet-stream")


def make_dispatch_ticket(index: int = 1) -> DispatchTicket:
    return DispatchTicket(
        index=index,
        tan_no=f"TAN#{index}",
        customer_pos=[],
        remark="",
        cartons=Decimal("1"),
        gross_weight=Decimal("1"),
        pallets=Decimal("1"),
        row_start=0,
        row_end=0,
    )


def make_dispatch_result(tmp_path: Path, ticket: DispatchTicket) -> DispatchParseResult:
    return DispatchParseResult(
        session_id="test-session",
        eml_name="source.eml",
        attachments_dir=tmp_path,
        output_dir=tmp_path,
        master=None,
        tickets=[ticket],
    )


def test_resolve_assignments_can_reclassify_so_as_dqth(tmp_path) -> None:
    ticket = make_dispatch_ticket()
    attachment = make_dispatch_attachment(tmp_path, "delivery-order.pdf")
    so = DispatchSo(attachment=attachment, preview_index=0)
    result = make_dispatch_result(tmp_path, ticket)
    result.sos = [so]

    resolve_assignments(result, {"dqth_match_1": "so:0"})

    assert len(result.dqths) == 1
    assert ticket.dqth is result.dqths[0]
    assert ticket.dqth.attachment is attachment
    assert ticket.dqth.matched_ticket_index == 0
    assert so.matched_ticket_index is None
    assert result.unmatched_sos == []


def test_resolve_assignments_can_reclassify_dqth_as_so(tmp_path) -> None:
    ticket = make_dispatch_ticket()
    attachment = make_dispatch_attachment(tmp_path, "packing-list.xlsx")
    dqth = DispatchDqth(
        attachment=attachment,
        customer_pos=[],
        cartons=Decimal("0"),
        gross_weight=Decimal("0"),
        pallets=Decimal("0"),
        preview_index=0,
    )
    result = make_dispatch_result(tmp_path, ticket)
    result.dqths = [dqth]

    resolve_assignments(result, {"so_match_1": "dqth:0"})

    assert len(result.sos) == 1
    assert ticket.so is result.sos[0]
    assert ticket.so.attachment is attachment
    assert ticket.so.matched_ticket_index == 0
    assert dqth.matched_ticket_index is None
    assert result.unmatched_dqths == []


def test_resolve_assignments_preserves_multi_pl_when_primary_is_unchanged(tmp_path) -> None:
    ticket = make_dispatch_ticket()
    attachments = [
        make_dispatch_attachment(tmp_path, "packing-list-1.xlsx"),
        make_dispatch_attachment(tmp_path, "packing-list-2.xlsx"),
    ]
    dqths = [
        DispatchDqth(
            attachment=attachment,
            customer_pos=[],
            cartons=Decimal("0"),
            gross_weight=Decimal("0"),
            pallets=Decimal("0"),
            preview_index=index,
            matched_ticket_index=0,
        )
        for index, attachment in enumerate(attachments)
    ]
    ticket.dqths = list(dqths)
    ticket.dqth = dqths[0]
    result = make_dispatch_result(tmp_path, ticket)
    result.dqths = dqths

    resolve_assignments(result, {"dqth_match_1": "dqth:0"})

    assert ticket_dqths(ticket) == dqths
    assert [dqth.matched_ticket_index for dqth in dqths] == [0, 0]


def test_flex_rtx_allows_multiple_pls_when_combined_totals_match() -> None:
    ticket = make_flex_ticket(1, ["PO1", "PO2"], "15", "2", "150")
    pls = [
        make_flex_pl(["PO1"], "5", "1", "50"),
        make_flex_pl(["PO2"], "10", "1", "100"),
    ]
    warnings: list[str] = []

    match_flex_rtx_dqths([ticket], pls, warnings)

    assert ticket_dqths(ticket) == pls
    assert [pl.matched_ticket_index for pl in pls] == [0, 0]
    assert warnings == []


def test_flex_rtx_does_not_swallow_shared_po_pls_when_ambiguous() -> None:
    tan1 = make_flex_ticket(1, ["PO1", "PO2"], "15", "2", "150")
    tan2 = make_flex_ticket(2, ["PO1"], "5", "1", "50")
    pls = [
        make_flex_pl(["PO1"], "5", "1", "50"),
        make_flex_pl(["PO2"], "10", "1", "100"),
    ]
    warnings: list[str] = []

    match_flex_rtx_dqths([tan1, tan2], pls, warnings)

    assert ticket_dqths(tan1) == []
    assert pls[0].matched_ticket_index is None
    assert any("共享 PO" in warning for warning in warnings)
