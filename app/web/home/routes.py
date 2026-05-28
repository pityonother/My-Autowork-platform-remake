from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.factory import create_templates
from app.module_catalog import MODULE_CATALOG


router = APIRouter()
templates = create_templates()


def module_cards() -> list[dict[str, str]]:
    return [
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


@router.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "index.html", {"modules": module_cards()})
