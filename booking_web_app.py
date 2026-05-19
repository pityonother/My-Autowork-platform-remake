from __future__ import annotations

from fastapi.responses import RedirectResponse

from app.factory import create_app
from app.modules.booking.routes import router as booking_router


app = create_app("Booking 生成器", routers=[booking_router])


@app.get("/")
async def index() -> RedirectResponse:
    return RedirectResponse(url="/modules/booking")
