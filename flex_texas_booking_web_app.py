from __future__ import annotations

import os

from fastapi.responses import RedirectResponse

os.environ.setdefault("BOOKING_LOCK_SUPPLIER", "FLEX-TEXAS")

from booking_web_app import create_booking_app  # noqa: E402


app = create_booking_app("Flex-Texas Booking 生成器")


@app.get("/")
async def index() -> RedirectResponse:
    return RedirectResponse(url="/modules/booking?supplier=FLEX-TEXAS")
