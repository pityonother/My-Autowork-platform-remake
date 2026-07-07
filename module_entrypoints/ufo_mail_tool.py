from __future__ import annotations

from app.factory import create_app, ensure_runtime_dirs
from app.modules.ufo_mail.repository import init_ufo_db
from app.modules.ufo_mail.routes import router
from app.packaging.local_server import run_local_app


app = create_app("UFO 邮件生成器", routers=[router], db_initializers=[init_ufo_db], init_runtime=False)


def main() -> None:
    ensure_runtime_dirs()
    init_ufo_db()
    run_local_app(app, display_name="UFO 邮件生成器", start_port=8036, landing_path="/modules/ufo-mail")


if __name__ == "__main__":
    main()
