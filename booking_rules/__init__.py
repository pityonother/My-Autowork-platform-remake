from __future__ import annotations

from . import sil, vc_dzyq, weikeng

SUPPLIER_RULES = {
    sil.SUPPLIER_NAME: sil,
    vc_dzyq.SUPPLIER_NAME: vc_dzyq,
    weikeng.SUPPLIER_NAME: weikeng,
}


def get_supplier_names() -> list[str]:
    return sorted(SUPPLIER_RULES.keys())
