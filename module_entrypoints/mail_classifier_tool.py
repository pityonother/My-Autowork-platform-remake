from __future__ import annotations

from app.factory import create_app
from app.modules.mail_classifier.routes import router
from app.packaging.local_server import run_local_app
from mail_classifier_store import init_mail_classifier_db


app = create_app("邮件标签分类器", routers=[router], db_initializers=[init_mail_classifier_db])


def main() -> None:
    run_local_app(app, display_name="邮件标签分类器", start_port=8035, landing_path="/modules/mail-classifier")


if __name__ == "__main__":
    main()
