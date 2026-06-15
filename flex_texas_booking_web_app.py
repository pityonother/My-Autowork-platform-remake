from __future__ import annotations

import os

from fastapi.responses import RedirectResponse

os.environ.setdefault("BOOKING_LOCK_SUPPLIER", "FLEX-TEXAS")

from app.factory import create_app  # noqa: E402
from app.modules.booking.routes import router as booking_router  # noqa: E402


app = create_app("Flex-Texas Booking 生成器", routers=[booking_router])


@app.get("/")
async def index() -> RedirectResponse:
    return RedirectResponse(url="/modules/booking?supplier=FLEX-TEXAS")
