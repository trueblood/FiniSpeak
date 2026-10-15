"""Read-only Firestore/MySQL reconciliation using canonical content hashes."""

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import create_app
from extensions import db as sql_db
from scripts.migrate_firestore_to_mysql import COLLECTIONS
from scripts.sync_firestore_to_mysql import snapshots
from services.synchronization_service import (
    reconcile_documents, safe_identifier_fingerprint, validate_firestore_project,
)


LOGGER = logging.getLogger("finispeak.firestore_mysql_reconciliation")


def source_documents(firestore, spec):
    result = {}
    for snapshot, parent_id in snapshots(firestore, spec):
        key = f"{parent_id}/{snapshot.id}" if parent_id else snapshot.id
        result[key] = snapshot.to_dict()
    return result


def target_documents(session, spec):
    rows = session.query(spec.model).all()
    result = {}
    for row in rows:
        primary = tuple(getattr(row, column.key) for column in spec.model.__mapper__.primary_key)
        key = f"{primary[0]}/{primary[1]}" if len(primary) > 1 else str(primary[0])
        # raw_document is the canonical Firestore payload. Mutation versions,
        # migration timestamps, generated columns, and outbox state are
        # deliberately excluded from content comparison.
        result[key] = dict(row.raw_document or {})
    return result


def reconcile_all(firestore, session):
    validate_firestore_project(firestore)
    report = {}
    for spec in COLLECTIONS:
        result = reconcile_documents(source_documents(firestore, spec), target_documents(session, spec))
        report[spec.name] = result
        LOGGER.info(
            "%s source=%s target=%s missing=%s extra=%s mismatched=%s identifiers=%s",
            spec.name, result.source_count, result.target_count, len(result.missing_target),
            len(result.extra_target), len(result.content_mismatches),
            [safe_identifier_fingerprint(key) for key in
             (*result.missing_target, *result.extra_target, *result.content_mismatches)[:20]],
        )
    return report


def reconciliation_succeeded(report, allow_target_additions=False):
    for result in report.values():
        if result.missing_target or result.content_mismatches:
            return False
        if result.extra_target and not allow_target_additions:
            return False
    return True


def main(argv=None):
    from services.firebase_service import get_db as get_firestore_db
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--allow-target-additions",
        action="store_true",
        help=("Permit MySQL-only records created after cutover while still failing "
              "for missing or content-mismatched imported records."),
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    app = create_app()
    if "sqlalchemy" not in app.extensions:
        raise RuntimeError("Complete MYSQL_* configuration is required.")
    with app.app_context():
        report = reconcile_all(get_firestore_db(), sql_db.session)
    return 0 if reconciliation_succeeded(report, args.allow_target_additions) else 1


if __name__ == "__main__":
    raise SystemExit(main())
