from __future__ import annotations

from . import flex_texas, sil, vc_dzyq, weikeng

SUPPLIER_RULES = {
    flex_texas.SUPPLIER_NAME: flex_texas,
    sil.SUPPLIER_NAME: sil,
    vc_dzyq.SUPPLIER_NAME: vc_dzyq,
    weikeng.SUPPLIER_NAME: weikeng,
}


def get_supplier_names() -> list[str]:
    return sorted(SUPPLIER_RULES.keys())
