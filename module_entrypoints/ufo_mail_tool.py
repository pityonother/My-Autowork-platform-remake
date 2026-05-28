from __future__ import annotations

from app.factory import create_app
from app.modules.ufo_mail.routes import router
from app.packaging.local_server import run_local_app
from ufo_mail_store import init_ufo_db


app = create_app("UFO 邮件生成器", routers=[router], db_initializers=[init_ufo_db])


def main() -> None:
    run_local_app(app, display_name="UFO 邮件生成器", start_port=8036, landing_path="/modules/ufo-mail")


if __name__ == "__main__":
    main()
