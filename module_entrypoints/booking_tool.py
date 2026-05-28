from __future__ import annotations

from app.factory import create_app
from app.modules.booking.routes import router
from app.packaging.local_server import run_local_app


app = create_app("Booking 生成器", routers=[router])


def main() -> None:
    run_local_app(app, display_name="Booking 生成器", start_port=8038, landing_path="/modules/booking")


if __name__ == "__main__":
    main()
