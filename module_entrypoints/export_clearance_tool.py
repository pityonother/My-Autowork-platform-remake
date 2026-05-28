from __future__ import annotations

from app.factory import create_app
from app.modules.export_clearance.routes import router
from app.packaging.local_server import run_local_app
from export_clearance_store import init_db as init_export_clearance_db


app = create_app("香港出口清关", routers=[router], db_initializers=[init_export_clearance_db])


def main() -> None:
    run_local_app(app, display_name="香港出口清关", start_port=8033, landing_path="/modules/export-customs")


if __name__ == "__main__":
    main()
