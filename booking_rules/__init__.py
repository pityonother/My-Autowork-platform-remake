from __future__ import annotations

from . import sil, weikeng

SUPPLIER_RULES = {
    sil.SUPPLIER_NAME: sil,
    weikeng.SUPPLIER_NAME: weikeng,
}


def get_supplier_names() -> list[str]:
    return sorted(SUPPLIER_RULES.keys())
