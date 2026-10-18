#!/usr/bin/env python3
"""Send first-party activation links to imported users lacking credentials."""

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from flask import Flask
from sqlalchemy import select

from app import configure_optional_mysql
from extensions import db
from models.sql_models import SqlAuthCredential, SqlUser
from services.auth_service import issue_action_token
from services.email_service import send_account_link


LOGGER = logging.getLogger("finispeak.account_activation")


def pending_users(user_id=None, limit=1000):
    query = select(SqlUser).outerjoin(SqlAuthCredential, SqlAuthCredential.user_id == SqlUser.id).where(
        SqlAuthCredential.user_id.is_(None), SqlUser.email.is_not(None), SqlUser.email != "")
    if user_id: query = query.where(SqlUser.id == user_id)
    return list(db.session.scalars(query.limit(limit)).all())


def main():
    parser = argparse.ArgumentParser(description="Dry-run or send activation links without logging identity data.")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--user-id", help="Target one imported user ID")
    parser.add_argument("--limit", type=int, default=1000)
    args = parser.parse_args()
    if not 1 <= args.limit <= 10000: parser.error("--limit must be between 1 and 10000")
    app = Flask("finispeak-account-activation"); configure_optional_mysql(app)
    if not app.config.get("MYSQL_CONFIGURED"): raise SystemExit("All MYSQL_* variables are required.")
    sent = failed = 0
    with app.app_context():
        users = pending_users(args.user_id, args.limit)
        if args.apply:
            for user in users:
                try:
                    token = issue_action_token(user.id, "reset_password")
                    send_account_link(user.email, "Activate your FiniSpeak account", "/reset-password", token)
                    sent += 1
                except Exception:
                    failed += 1
                    LOGGER.error("account_activation_delivery_failed")
    LOGGER.info("account_activation_complete dry_run=%s eligible=%d sent=%d failed=%d", not args.apply, len(users), sent, failed)
    if failed: raise SystemExit(1)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    main()
