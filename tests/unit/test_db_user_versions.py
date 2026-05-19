from __future__ import annotations

import dispatch_mail_store
import export_clearance_store
import finance_store
import mail_classifier_store
import ufo_mail_store


def test_legacy_store_initializers_set_user_version(monkeypatch, tmp_path) -> None:
    stores = [
        (export_clearance_store, "init_db", "export_clearance.db"),
        (finance_store, "init_finance_db", "finance_records.db"),
        (dispatch_mail_store, "init_dispatch_db", "dispatch_mail.db"),
        (mail_classifier_store, "init_mail_classifier_db", "mail_classifier.db"),
        (ufo_mail_store, "init_ufo_db", "ufo_mail.db"),
    ]

    for module, init_name, db_name in stores:
        monkeypatch.setattr(module, "DB_PATH", tmp_path / db_name)
        getattr(module, init_name)()
        with module.get_connection() as conn:
            assert conn.execute("PRAGMA user_version").fetchone()[0] == 1


def test_legacy_store_initializers_upgrade_existing_user_version_zero_db(monkeypatch, tmp_path) -> None:
    stores = [
        (export_clearance_store, "init_db", "export_clearance.db"),
        (finance_store, "init_finance_db", "finance_records.db"),
        (dispatch_mail_store, "init_dispatch_db", "dispatch_mail.db"),
        (mail_classifier_store, "init_mail_classifier_db", "mail_classifier.db"),
        (ufo_mail_store, "init_ufo_db", "ufo_mail.db"),
    ]

    for module, init_name, db_name in stores:
        db_path = tmp_path / db_name
        monkeypatch.setattr(module, "DB_PATH", db_path)
        with module.get_connection() as conn:
            conn.execute("CREATE TABLE legacy_marker (id INTEGER PRIMARY KEY)")
            conn.execute("INSERT INTO legacy_marker (id) VALUES (1)")
            conn.execute("PRAGMA user_version = 0")

        getattr(module, init_name)()

        with module.get_connection() as conn:
            assert conn.execute("PRAGMA user_version").fetchone()[0] == 1
            assert conn.execute("SELECT id FROM legacy_marker").fetchone()[0] == 1
