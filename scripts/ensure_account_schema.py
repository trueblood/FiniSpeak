#!/usr/bin/env python3
"""Add the account columns the running app expects without moving Alembic.

The installed root deploy helper still requires schema revision 20261014_0003.
Login fails when the newer code selects users.deleted_at before that helper can
apply 20261016_0004. This adds only the missing objects and leaves the revision
stamp alone so the helper can still restart the service.
"""

import re
import sys
from pathlib import Path

from sqlalchemy import inspect, text

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import create_app
from extensions import db
from models.sql_models import SqlFriend


def _mysql_identifier(value):
    if not re.fullmatch(r"[A-Za-z0-9_]+", value or ""):
        raise RuntimeError(f"unexpected MySQL identifier: {value}")
    return value


def friends_table_ddl(charset, collation):
    charset = _mysql_identifier(charset)
    collation = _mysql_identifier(collation)
    string = f"VARCHAR(128) CHARACTER SET {charset} COLLATE {collation} NOT NULL"
    short = f"CHARACTER SET {charset} COLLATE {collation}"
    return f"""CREATE TABLE friends (
        owner_id {string},
        friend_id {string},
        nickname VARCHAR(160) {short} NULL,
        saved_phone VARCHAR(64) {short} NULL,
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        PRIMARY KEY (owner_id, friend_id),
        KEY ix_friends_friend_id (friend_id),
        CONSTRAINT fk_friends_owner_id_users FOREIGN KEY (owner_id) REFERENCES users (id) ON DELETE CASCADE,
        CONSTRAINT fk_friends_friend_id_users FOREIGN KEY (friend_id) REFERENCES users (id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET={charset} COLLATE={collation}"""


def _users_id_charset(connection):
    row = connection.execute(text("""
        SELECT CHARACTER_SET_NAME AS charset_name, COLLATION_NAME AS collation_name
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'users' AND COLUMN_NAME = 'id'
    """)).mappings().one()
    return row["charset_name"], row["collation_name"]


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
        if connection.dialect.name == "mysql":
            charset, collation = _users_id_charset(connection)
            charset, collation = _mysql_identifier(charset), _mysql_identifier(collation)
            connection.execute(text(
                "ALTER TABLE users ADD COLUMN deleted_by "
                f"VARCHAR(128) CHARACTER SET {charset} COLLATE {collation} NULL"
            ))
        else:
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
        if connection.dialect.name == "mysql":
            charset, collation = _users_id_charset(connection)
            connection.execute(text(friends_table_ddl(charset, collation)))
        else:
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
