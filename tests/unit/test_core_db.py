from __future__ import annotations

import sqlite3

from app.core.db import connect, run_migrations, table_has_column


def test_connect_sets_row_factory_and_pragmas(tmp_path) -> None:
    db_path = tmp_path / "sample.db"
    with connect(db_path) as conn:
        conn.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY, name TEXT)")
        conn.execute("INSERT INTO sample (name) VALUES ('alpha')")
        row = conn.execute("SELECT name FROM sample").fetchone()
        assert isinstance(row, sqlite3.Row)
        assert row["name"] == "alpha"
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_run_migrations_advances_user_version(tmp_path) -> None:
    db_path = tmp_path / "sample.db"
    with connect(db_path) as conn:
        run_migrations(conn, {1: lambda c: c.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY)")})
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 1
        assert table_has_column(conn, "sample", "id")
