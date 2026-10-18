#!/usr/bin/env python3
"""Set one test-server account password without exposing it in shell history."""

import argparse
import getpass
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from flask import Flask

from app import configure_optional_mysql
from services.auth_service import (
    AuthenticationError,
    AuthorizationError,
    set_test_account_password,
)


LOGGER = logging.getLogger("finispeak.test_account_password")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user-id", required=True, help="Exact preserved account document ID")
    args = parser.parse_args(argv)

    password = getpass.getpass("New password: ")
    confirmation = getpass.getpass("Confirm new password: ")
    if password != confirmation:
        raise SystemExit("Passwords do not match.")

    app = Flask("finispeak-test-account-password")
    configure_optional_mysql(app)
    if not app.config.get("MYSQL_CONFIGURED"):
        raise SystemExit("All MYSQL_* variables are required.")
    try:
        with app.app_context():
            set_test_account_password(args.user_id, password)
    except (AuthenticationError, AuthorizationError, ValueError) as exc:
        raise SystemExit(str(exc)) from None
    LOGGER.info("test_account_password_updated")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    raise SystemExit(main())
