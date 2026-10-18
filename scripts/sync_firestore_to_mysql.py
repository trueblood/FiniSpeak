"""Operator-run Firestore-primary snapshot catch-up for MySQL.

Dry-run is the default. Applying requires both ``--apply`` and
FINISPEAK_FIRESTORE_MYSQL_SYNC_ENABLED=true. Deletions additionally require a
second explicit flag and two complete scans that observe the same absence.
"""

import argparse
import hashlib
import logging
from datetime import datetime, timezone

from app import create_app
from extensions import db as sql_db
from models.sql_models import SqlSyncCheckpoint
from scripts.migrate_firestore_to_mysql import COLLECTIONS
from services.synchronization_service import (
    DeletionConfirmation, MirrorEvent, SqlAlchemySyncStore,
    SynchronizationEngine, snapshot_event, synchronization_flags,
    validate_firestore_project,
)


LOGGER = logging.getLogger("finispeak.firestore_mysql_sync")
DELETE_SOURCE = "firestore_snapshot_deletions"


def snapshots(firestore, spec):
    if spec.parent_source is None:
        for snapshot in firestore.collection(spec.source).stream():
            yield snapshot, None
        return
    for parent in firestore.collection(spec.parent_source).stream():
        for snapshot in parent.reference.collection(spec.source).stream():
            yield snapshot, parent.id


def candidate_checkpoint(session, collection):
    checkpoint_id = f"firestore-delete-scan:{collection}"
    checkpoint = session.get(SqlSyncCheckpoint, checkpoint_id)
    return checkpoint, set((checkpoint.cursor or {}).get("candidates", [])) if checkpoint else set()


def save_candidates(session, collection, candidates, scan_started):
    checkpoint, _ = candidate_checkpoint(session, collection)
    checkpoint_id = f"firestore-delete-scan:{collection}"
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if not checkpoint:
        checkpoint = SqlSyncCheckpoint(
            id=checkpoint_id, source=DELETE_SOURCE, collection_name=collection,
            status="idle", records_scanned=0, records_applied=0,
            error_count=0, created_at=now, updated_at=now,
        )
        session.add(checkpoint)
    checkpoint.cursor = {"candidates": sorted(candidates)}
    checkpoint.high_watermark = scan_started
    checkpoint.records_scanned = int(checkpoint.records_scanned or 0) + 1
    checkpoint.updated_at = now


def run_sync(firestore, session, apply=False, apply_deletions=False, retries=3, logger=LOGGER):
    flags = synchronization_flags()
    if apply and not flags["enabled"]:
        raise RuntimeError("Synchronization apply is disabled. Set the explicit Phase 3 enable flag.")
    if apply_deletions and not (apply and flags["deletions_enabled"]):
        raise RuntimeError("Deletion apply requires both synchronization and deletion enable flags.")
    validate_firestore_project(firestore, require_expected=apply_deletions)

    scan_started = datetime.now(timezone.utc).replace(tzinfo=None)
    store = SqlAlchemySyncStore(session)
    engine = SynchronizationEngine(store, retries=retries)
    source_keys, events_by_collection = {}, {}
    report = {"dry_run": not apply, "upserts": 0, "duplicates": 0, "stale": 0,
              "ordering_conflicts": 0, "delete_candidates": 0, "deletions": 0, "errors": 0}

    # A complete enumeration is essential: browser writes do not pass through
    # backend dual-write hooks. Any scan exception aborts before candidate state
    # is advanced, so a partial source listing cannot authorize deletions.
    for spec in COLLECTIONS:
        keys, events = set(), []
        for snapshot, parent_id in snapshots(firestore, spec):
            event = snapshot_event(spec, snapshot, parent_id)
            keys.add(event.record_key)
            events.append(event)
        source_keys[spec.name], events_by_collection[spec.name] = keys, events
        logger.info("Firestore snapshot %s: %s record(s)", spec.name, len(keys))

    if apply:
        for spec in COLLECTIONS:
            for event in events_by_collection[spec.name]:
                try:
                    result = engine.apply(event)
                    key = {"applied": "upserts", "duplicate": "duplicates", "stale": "stale",
                           "ordering_conflict": "ordering_conflicts"}[result.status]
                    report[key] += 1
                except Exception as exc:
                    report["errors"] += 1
                    logger.error("%s mirror failed (%s)", spec.name, type(exc).__name__)
    else:
        report["upserts"] = sum(len(events) for events in events_by_collection.values())

    deletion_events = []
    can_advance_deletions = apply and report["errors"] == 0
    for spec in COLLECTIONS:
        target = store.target_keys(spec.name)
        checkpoint, previous = candidate_checkpoint(session, spec.name)
        current, confirmed = DeletionConfirmation.confirm(previous, source_keys[spec.name], target)
        report["delete_candidates"] += len(current)
        if can_advance_deletions:
            save_candidates(session, spec.name, current, scan_started)
            session.commit()
        if apply_deletions and can_advance_deletions:
            for record_key in confirmed:
                parent_id, document_id = (record_key.split("/", 1) if spec.parent_source else (None, record_key))
                event_id = hashlib.sha256(
                    f"delete|{spec.name}|{record_key}|{scan_started.isoformat()}".encode("utf-8")
                ).hexdigest()
                deletion_events.append(MirrorEvent(
                    spec.name, document_id, "delete", scan_started, event_id, parent_id=parent_id,
                ))

    # Children are deleted before parents to respect restrictive relationships.
    order = {spec.name: index for index, spec in enumerate(COLLECTIONS)}
    for event in sorted(deletion_events, key=lambda item: order[item.collection], reverse=True):
        try:
            if engine.apply(event).status == "applied": report["deletions"] += 1
        except Exception as exc:
            report["errors"] += 1
            logger.error("%s deletion mirror failed (%s)", event.collection, type(exc).__name__)

    report["partial"] = report["errors"] > 0
    report["deletion_checkpoint_advanced"] = can_advance_deletions
    return report


def main(argv=None):
    from services.firebase_service import get_db as get_firestore_db
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Apply upserts to MySQL; otherwise only scan and report.")
    parser.add_argument("--apply-deletions", action="store_true", help="Apply twice-confirmed deletions; requires --apply and deletion flag.")
    parser.add_argument("--retries", type=int, default=3)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    app = create_app()
    if "sqlalchemy" not in app.extensions:
        raise RuntimeError("Complete MYSQL_* configuration is required.")
    with app.app_context():
        report = run_sync(get_firestore_db(), sql_db.session, args.apply, args.apply_deletions, args.retries)
    LOGGER.info("Sync summary: %s", report)
    return 1 if report["partial"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
