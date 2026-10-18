#!/usr/bin/env python3
"""Safely standardize FiniSpeak phone fields to E.164 storage.

The command is a dry run unless --apply is supplied. It refuses to write when
invalid or duplicate account numbers remain because phone lookup would be
ambiguous. Specific obsolete accounts can be cleared with repeatable
--clear-phone EMAIL arguments.
"""

import argparse
import json
import sys
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask
from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import configure_optional_mysql
from extensions import db
from models.sql_models import SqlInterpreterPrivate, SqlUser
from repositories.normalization import canonicalize_phone, normalize_email, normalize_phone


def build_report(users, private_profiles, default_calling_code="1", clear_emails=()):
    clear_emails = {normalize_email(value) for value in clear_emails if normalize_email(value)}
    account_changes, private_changes, invalid = [], [], []
    by_number = defaultdict(list)

    for user in users:
        email = normalize_email(user.email)
        original = str(user.phone or "").strip()
        clear = email in clear_emails
        canonical = "" if clear else canonicalize_phone(original, default_calling_code)
        if original and not clear and not canonical:
            invalid.append({"type": "account", "id": user.id, "email": email, "phone": original})
            continue
        normalized = normalize_phone(canonical)
        if normalized:
            by_number[normalized].append({"id": user.id, "email": email})
        if original != canonical or str(user.phone_normalized or "") != normalized:
            account_changes.append({
                "row": user,
                "id": user.id,
                "email": email,
                "from": original,
                "to": canonical,
                "normalized": normalized,
            })

    for profile in private_profiles:
        email = normalize_email(profile.email)
        original = str(profile.phone or "").strip()
        clear = email in clear_emails
        canonical = "" if clear else canonicalize_phone(original, default_calling_code)
        if original and not clear and not canonical:
            invalid.append({"type": "interpreter_private", "id": profile.id, "email": email, "phone": original})
            continue
        if original != canonical:
            private_changes.append({"row": profile, "id": profile.id, "email": email, "from": original, "to": canonical})

    duplicates = [
        {"normalized": number, "accounts": accounts}
        for number, accounts in sorted(by_number.items())
        if len(accounts) > 1
    ]
    return {
        "account_changes": account_changes,
        "private_changes": private_changes,
        "invalid": invalid,
        "duplicates": duplicates,
        "clear_emails": sorted(clear_emails),
    }


def public_report(report, applied=False):
    return {
        "mode": "apply" if applied else "dry-run",
        "accountChanges": [{key: value for key, value in item.items() if key != "row"} for item in report["account_changes"]],
        "interpreterPrivateChanges": [{key: value for key, value in item.items() if key != "row"} for item in report["private_changes"]],
        "invalid": report["invalid"],
        "duplicates": report["duplicates"],
        "clearEmails": report["clear_emails"],
        "safeToApply": not report["invalid"] and not report["duplicates"],
        "applied": applied,
    }


def apply_report(report):
    if report["invalid"] or report["duplicates"]:
        raise ValueError("Resolve invalid or duplicate phone numbers before applying changes.")
    now = datetime.now(timezone.utc)
    for item in report["account_changes"]:
        row = item["row"]
        raw = dict(row.raw_document or {})
        raw.update({"phone": item["to"], "phoneNormalized": item["normalized"]})
        row.phone = item["to"]
        row.phone_normalized = item["normalized"]
        row.raw_document = raw
        row.updated_at = now
        row.source_updated_at = now
        row.mutation_version = int(row.mutation_version or 0) + 1
        row.last_mutation_id = uuid.uuid4().hex
    for item in report["private_changes"]:
        row = item["row"]
        raw = dict(row.raw_document or {})
        raw["phone"] = item["to"]
        row.phone = item["to"]
        row.raw_document = raw
        row.updated_at = now
        row.source_updated_at = now
        row.mutation_version = int(row.mutation_version or 0) + 1
        row.last_mutation_id = uuid.uuid4().hex
    db.session.commit()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Standardize FiniSpeak MySQL phone numbers to E.164.")
    parser.add_argument("--apply", action="store_true", help="Commit the reported changes. The default is dry-run.")
    parser.add_argument("--default-calling-code", default="1", help="Calling code for legacy 10-digit local numbers (default: 1).")
    parser.add_argument("--clear-phone", action="append", default=[], metavar="EMAIL", help="Clear a specific obsolete account phone; repeat as needed.")
    args = parser.parse_args(argv)

    app = Flask("finispeak-standardize-phone-numbers")
    configure_optional_mysql(app)
    if not app.config.get("MYSQL_CONFIGURED"):
        raise SystemExit("All MYSQL_* variables are required.")
    with app.app_context():
        users = db.session.scalars(select(SqlUser).order_by(SqlUser.email_normalized, SqlUser.id)).all()
        private_profiles = db.session.scalars(select(SqlInterpreterPrivate).order_by(SqlInterpreterPrivate.id)).all()
        report = build_report(users, private_profiles, args.default_calling_code, args.clear_phone)
        if args.apply:
            try:
                apply_report(report)
            except Exception:
                db.session.rollback()
                print(json.dumps(public_report(report), indent=2, sort_keys=True))
                raise
        print(json.dumps(public_report(report, applied=args.apply), indent=2, sort_keys=True))
        if report["invalid"] or report["duplicates"]:
            raise SystemExit(2)


if __name__ == "__main__":
    main()
