from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.factory import create_templates
from app.module_catalog import MODULE_CATALOG


router = APIRouter()
templates = create_templates()


def module_cards() -> list[dict[str, str]]:
    cards = [
        {
            "title": module.title,
            "icon": module.title[:1].upper(),
            "badge": module.badge,
            "subtitle": module.subtitle,
            "description": module.description,
            "href": module.route_path,
        }
        for module in MODULE_CATALOG
    ]
    cards.append(
        {
            "title": "Flex-Texas Booking",
            "icon": "F",
            "badge": "PDF 对照",
            "subtitle": "客户 eml 到 booking form",
            "description": "上传 FLEX-TEXAS 原始 eml，读取邮件正文和 PDF 附件，自动转出 TIF 用照片查看器核对，再生成 booking form。",
            "href": "/modules/booking?supplier=FLEX-TEXAS",
        }
    )
    return cards


@router.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "index.html", {"modules": module_cards()})
