from __future__ import annotations

from app.factory import create_app
from app.modules.dispatch_mail.routes import router
from app.packaging.local_server import run_local_app
from dispatch_mail_store import init_dispatch_db


app = create_app("派送邮件生成器", routers=[router], db_initializers=[init_dispatch_db])


def main() -> None:
    run_local_app(app, display_name="派送邮件生成器", start_port=8037, landing_path="/modules/dispatch-mail")


if __name__ == "__main__":
    main()
