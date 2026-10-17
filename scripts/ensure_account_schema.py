#!/usr/bin/env python3
"""Add the account columns the running app expects without moving Alembic.

The installed root deploy helper still requires schema revision 20261014_0003.
Login fails when the newer code selects users.deleted_at before that helper can
apply 20261016_0004. This adds only the missing objects and leaves the revision
stamp alone so the helper can still restart the service.
"""

import sys
from pathlib import Path

from sqlalchemy import inspect, text

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import create_app
from extensions import db
from models.sql_models import SqlFriend


def ensure_account_schema(connection):
    inspector = inspect(connection)
    if "users" not in inspector.get_table_names():
        return []
    changes = []
    columns = {column["name"] for column in inspector.get_columns("users")}
    if "deleted_at" not in columns:
        connection.execute(text("ALTER TABLE users ADD COLUMN deleted_at DATETIME NULL"))
        changes.append("users.deleted_at")
    if "deleted_by" not in columns:
        connection.execute(text("ALTER TABLE users ADD COLUMN deleted_by VARCHAR(128) NULL"))
        changes.append("users.deleted_by")
    if connection.dialect.name == "mysql":
        inspector = inspect(connection)
        indexes = {item["name"] for item in inspector.get_indexes("users")}
        if "ix_users_deleted_at" not in indexes:
            connection.execute(text("CREATE INDEX ix_users_deleted_at ON users (deleted_at)"))
            changes.append("ix_users_deleted_at")
        foreign_keys = {item.get("name") for item in inspector.get_foreign_keys("users")}
        if "fk_users_deleted_by_users" not in foreign_keys:
            connection.execute(text(
                "ALTER TABLE users ADD CONSTRAINT fk_users_deleted_by_users "
                "FOREIGN KEY (deleted_by) REFERENCES users (id) ON DELETE SET NULL"
            ))
            changes.append("fk_users_deleted_by_users")
    if "friends" not in inspect(connection).get_table_names():
        SqlFriend.__table__.create(connection, checkfirst=True)
        changes.append("friends")
    return changes


def main():
    app = create_app()
    with app.app_context():
        with db.engine.begin() as connection:
            changes = ensure_account_schema(connection)
    print("account schema ensured: " + (", ".join(changes) if changes else "already current"))


if __name__ == "__main__":
    main()
