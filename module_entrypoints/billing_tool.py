from __future__ import annotations

from app.factory import create_app
from app.modules.billing.routes import router
from app.packaging.local_server import run_local_app


app = create_app("做账单", routers=[router])


def main() -> None:
    run_local_app(app, display_name="做账单", start_port=8031, landing_path="/modules/billing")


if __name__ == "__main__":
    main()
