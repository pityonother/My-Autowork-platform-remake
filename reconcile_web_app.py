from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.factory import create_app
from app.modules.billing.routes import router as billing_router
from app.modules.booking.routes import router as booking_router
from app.modules.booking.sil_fuca_delivery import (
    start_delivery_list_background_refresh,
    stop_delivery_list_background_refresh,
)
from app.modules.dispatch_mail.routes import router as dispatch_mail_router
from app.modules.export_clearance.routes import router as export_clearance_router
from app.modules.finance.routes import router as finance_router
from app.modules.import_customs.routes import router as import_customs_router
from app.modules.mail_classifier.routes import router as mail_classifier_router
from app.modules.ufo_mail.routes import router as ufo_mail_router
from app.web.home.routes import router as home_router
from dispatch_mail_store import init_dispatch_db
from export_clearance_store import init_db as init_export_clearance_db
from finance_store import init_finance_db
from mail_classifier_store import init_mail_classifier_db
from ufo_mail_store import init_ufo_db


@asynccontextmanager
async def app_lifespan(app: FastAPI) -> AsyncIterator[None]:
    start_delivery_list_background_refresh()
    try:
        yield
    finally:
        await stop_delivery_list_background_refresh()


app = create_app(
    "账单与清关工具",
    db_initializers=[
        init_export_clearance_db,
        init_finance_db,
        init_ufo_db,
        init_dispatch_db,
        init_mail_classifier_db,
    ],
    routers=[
        home_router,
        billing_router,
        booking_router,
        dispatch_mail_router,
        import_customs_router,
        export_clearance_router,
        finance_router,
        mail_classifier_router,
        ufo_mail_router,
    ],
    lifespan=app_lifespan,
)
