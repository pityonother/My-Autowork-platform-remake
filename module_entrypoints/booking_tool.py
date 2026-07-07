from __future__ import annotations

from booking_web_app import create_booking_app
from app.packaging.local_server import run_local_app


app = create_booking_app()


def main() -> None:
    run_local_app(app, display_name="Booking 生成器", start_port=8038, landing_path="/modules/booking")


if __name__ == "__main__":
    main()
