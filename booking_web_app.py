from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import RedirectResponse

from app.factory import create_app
from app.modules.booking.routes import router as booking_router
from app.modules.booking.sil_fuca_delivery import (
    start_delivery_list_background_refresh,
    stop_delivery_list_background_refresh,
)


@asynccontextmanager
async def booking_lifespan(app: FastAPI) -> AsyncIterator[None]:
    start_delivery_list_background_refresh()
    try:
        yield
    finally:
        await stop_delivery_list_background_refresh()


def create_booking_app(title: str = "Booking 生成器") -> FastAPI:
    return create_app(title, routers=[booking_router], lifespan=booking_lifespan)


app = create_booking_app()


@app.get("/")
async def index() -> RedirectResponse:
    return RedirectResponse(url="/modules/booking")
