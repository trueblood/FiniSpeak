#!/usr/bin/env python3
"""Report aggregate imported-account activation readiness without identities."""

import json
import sys
from pathlib import Path

from flask import Flask
from sqlalchemy import func, select

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import configure_optional_mysql
from extensions import db
from models.sql_models import SqlAuthCredential, SqlUser


def readiness_report():
    email_present = SqlUser.email.is_not(None) & (SqlUser.email != "")
    missing_normalized = db.session.scalar(select(func.count()).select_from(SqlUser).where(
        email_present, (SqlUser.email_normalized.is_(None)) | (SqlUser.email_normalized == "")
    ))
    duplicate_groups = db.session.scalar(select(func.count()).select_from(
        select(SqlUser.email_normalized).where(
            SqlUser.email_normalized.is_not(None), SqlUser.email_normalized != ""
        ).group_by(SqlUser.email_normalized).having(func.count() > 1).subquery()
    ))
    eligible = db.session.scalar(select(func.count()).select_from(SqlUser).outerjoin(
        SqlAuthCredential, SqlAuthCredential.user_id == SqlUser.id
    ).where(email_present, SqlAuthCredential.user_id.is_(None)))
    credentialed = db.session.scalar(select(func.count()).select_from(SqlAuthCredential))
    return {
        "eligibleImportedAccounts": int(eligible or 0),
        "credentialedAccounts": int(credentialed or 0),
        "missingNormalizedEmail": int(missing_normalized or 0),
        "duplicateNormalizedEmailGroups": int(duplicate_groups or 0),
    }


def main():
    app = Flask("finispeak-account-activation-readiness")
    configure_optional_mysql(app)
    if not app.config.get("MYSQL_CONFIGURED"):
        raise SystemExit("All MYSQL_* variables are required.")
    with app.app_context():
        report = readiness_report()
    print(json.dumps(report, sort_keys=True))
    if report["missingNormalizedEmail"] or report["duplicateNormalizedEmailGroups"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
