from __future__ import annotations

from app.factory import create_app, ensure_runtime_dirs
from app.modules.finance.repository import init_finance_db
from app.modules.finance.routes import router
from app.packaging.local_server import run_local_app


app = create_app("财务记录", routers=[router], db_initializers=[init_finance_db], init_runtime=False)


def main() -> None:
    ensure_runtime_dirs()
    init_finance_db()
    run_local_app(app, display_name="财务记录", start_port=8034, landing_path="/modules/finance-records")


if __name__ == "__main__":
    main()
