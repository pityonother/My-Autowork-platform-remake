from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.factory import create_templates


router = APIRouter()
templates = create_templates()


def module_cards() -> list[dict[str, str]]:
    return [
        {
            "title": "做账单",
            "icon": "B",
            "badge": "账单处理",
            "subtitle": "总账回填与单页账单核对",
            "description": "上传空白账单格式、派送单、单页账单和 Flex Tan# 总表，先预览再导出。",
            "href": "/modules/billing",
        },
        {
            "title": "香港进口清关",
            "icon": "I",
            "badge": "进口清关",
            "subtitle": "bill 模板回填",
            "description": "上传空白 bill、订单管理和真实数据源，查看中间态并导出进口清关结果。",
            "href": "/modules/import-customs",
        },
        {
            "title": "香港出口清关",
            "icon": "E",
            "badge": "历史批次",
            "subtitle": "带历史批次与待清关排序",
            "description": "上传 Flex Tan# 总表，保存历史批次、查看待清关优先级，并沿用旧项目导出逻辑。",
            "href": "/modules/export-customs",
        },
        {
            "title": "财务记录",
            "icon": "F",
            "badge": "持久化任务",
            "subtitle": "payment 到 OUTBOUND",
            "description": "记录代支任务、跟踪付款进度，并把福永伟创力代支按规则回填到 bill 的 OUTBOUND。",
            "href": "/modules/finance-records",
        },
        {
            "title": "邮件标签分类器",
            "icon": "M",
            "badge": "自动标签",
            "subtitle": "网易企业邮箱 到 业务标签",
            "description": "只读同步邮箱邮件，按出口订单、出口清关、代垫、发票等规则生成项目内标签，并支持人工确认。",
            "href": "/modules/mail-classifier",
        },
        {
            "title": "UFO邮件生成器",
            "icon": "U",
            "badge": "异常反馈",
            "subtitle": "问题库勾选生成 eml",
            "description": "维护常用异常反馈库，勾选问题并附上 UFO 文件和图片，自动生成英文邮件草稿。",
            "href": "/modules/ufo-mail",
        },
        {
            "title": "派送邮件生成器",
            "icon": "D",
            "badge": "派送邮件",
            "subtitle": "客户邮件 -> 仓库派送邮件",
            "description": "从客户邮件提取附件，自动改名、按 Tan# 拆段、生成发给仓库的 .eml。",
            "href": "/modules/dispatch-mail",
        },
        {
            "title": "Booking 生成器",
            "icon": "K",
            "badge": "自动填表",
            "subtitle": "CCIXLS -> booking form",
            "description": "上传客户 CCIXLS，自动按供应商规则生成 booking_template_zh 的填好稿。",
            "href": "/modules/booking",
        },
    ]


@router.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "index.html", {"modules": module_cards()})
