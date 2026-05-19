from __future__ import annotations

import sqlite3
from collections.abc import Callable
from pathlib import Path


Migration = Callable[[sqlite3.Connection], None]


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    return connection


def table_has_column(connection: sqlite3.Connection, table_name: str, column_name: str) -> bool:
    rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    return any(row["name"] == column_name for row in rows)


def run_migrations(connection: sqlite3.Connection, migrations: dict[int, Migration]) -> None:
    current = int(connection.execute("PRAGMA user_version").fetchone()[0])
    for version in sorted(migrations):
        if version > current:
            migrations[version](connection)
            connection.execute(f"PRAGMA user_version = {version}")
