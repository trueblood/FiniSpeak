#!/usr/bin/env python3
"""Verify private-storage rows and files without logging names or identities."""

import hashlib
import json
import os
import pwd
import stat
import sys
from pathlib import Path

from flask import Flask
from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import configure_optional_mysql
from extensions import db
from models.sql_models import SqlStoredFile, SqlUser


def verify():
    root = Path(os.environ.get("FINISPEAK_STORAGE_ROOT", "")).resolve()
    if not root.is_dir():
        raise RuntimeError("Private storage root is unavailable.")
    report = {"records": 0, "active": 0, "deleted": 0, "verified": 0,
              "missingOwners": 0, "missingFiles": 0, "hashMismatches": 0,
              "unexpectedFiles": 0, "wrongOwnership": 0, "unsafeModes": 0}
    owner_name = os.environ.get("FINISPEAK_STORAGE_OWNER", "").strip()
    expected_owner = pwd.getpwnam(owner_name) if owner_name else None
    root_stat = root.stat()
    if expected_owner and (root_stat.st_uid, root_stat.st_gid) != (
        expected_owner.pw_uid, expected_owner.pw_gid
    ):
        report["wrongOwnership"] += 1
    if stat.S_IMODE(root_stat.st_mode) != 0o750:
        report["unsafeModes"] += 1
    expected = set()
    rows = list(db.session.scalars(select(SqlStoredFile)).all())
    report["records"] = len(rows)
    for row in rows:
        if row.deleted_at:
            report["deleted"] += 1
            continue
        report["active"] += 1
        if not db.session.get(SqlUser, row.owner_id):
            report["missingOwners"] += 1
        target = (root / row.stored_name).resolve()
        if target.parent != root:
            report["missingFiles"] += 1
            continue
        expected.add(target.name)
        if not target.is_file():
            report["missingFiles"] += 1
            continue
        target_stat = target.stat()
        if expected_owner and (target_stat.st_uid, target_stat.st_gid) != (
            expected_owner.pw_uid, expected_owner.pw_gid
        ):
            report["wrongOwnership"] += 1
        if stat.S_IMODE(target_stat.st_mode) != 0o640:
            report["unsafeModes"] += 1
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        if digest != row.sha256 or target_stat.st_size != row.size_bytes:
            report["hashMismatches"] += 1
            continue
        report["verified"] += 1
    report["unexpectedFiles"] = sum(
        1 for path in root.iterdir() if path.is_file() and path.name not in expected
    )
    return report


def main():
    app = Flask("finispeak-private-storage-verification")
    configure_optional_mysql(app)
    if not app.config.get("MYSQL_CONFIGURED"):
        raise SystemExit("All MYSQL_* variables are required.")
    with app.app_context():
        report = verify()
    print(json.dumps(report, sort_keys=True))
    failed = sum(report[key] for key in
                 ("missingOwners", "missingFiles", "hashMismatches", "unexpectedFiles",
                  "wrongOwnership", "unsafeModes"))
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
