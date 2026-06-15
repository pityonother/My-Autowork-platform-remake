from __future__ import annotations

import os

os.environ.setdefault("BOOKING_LOCK_SUPPLIER", "FLEX-TEXAS")

from app.packaging.local_server import run_local_app  # noqa: E402
from flex_texas_booking_web_app import app  # noqa: E402


def main() -> None:
    run_local_app(
        app,
        display_name="Flex-Texas Booking 生成器",
        start_port=8021,
        landing_path="/modules/booking?supplier=FLEX-TEXAS",
    )


if __name__ == "__main__":
    main()
