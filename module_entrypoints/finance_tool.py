from __future__ import annotations

from app.factory import create_app
from app.modules.finance.routes import router
from app.packaging.local_server import run_local_app
from finance_store import init_finance_db


app = create_app("财务记录", routers=[router], db_initializers=[init_finance_db])


def main() -> None:
    run_local_app(app, display_name="财务记录", start_port=8034, landing_path="/modules/finance-records")


if __name__ == "__main__":
    main()
