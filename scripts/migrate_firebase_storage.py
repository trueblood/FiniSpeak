#!/usr/bin/env python3
"""Copy legacy Firebase Storage objects into private FiniSpeak storage.

Dry-run is the default. The source bucket is always read-only: this script
never updates metadata or deletes an object in Firebase Storage.
"""

import argparse
import hashlib
import json
import logging
import mimetypes
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Support the documented ``python scripts/...`` operator invocation without
# requiring an implicit PYTHONPATH or installation of the repository package.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from flask import Flask
from sqlalchemy import select

from app import configure_optional_mysql
from extensions import db
from models.sql_models import SqlInterpreterPrivate, SqlStoredFile, SqlTranslator, SqlUser
from services.file_storage_service import ALLOWED_TYPES, serialize_file, validate_file_content


LOGGER = logging.getLogger("finispeak.storage_migration")
NAMESPACE = uuid.UUID("b7a0aab9-e46e-4399-b726-848a52e34d20")


def fingerprint(bucket_name, object_name):
    return hashlib.sha256(f"{bucket_name}\0{object_name}".encode()).hexdigest()


def classify(object_name):
    parts = str(object_name or "").split("/")
    if len(parts) < 3 or not parts[1] or not parts[-1]:
        return None
    if parts[0] == "interpreter-profiles":
        return parts[1], "profile_photo"
    if parts[0] == "interpreter-credentials":
        return parts[1], "credential"
    return None


def validate_blob(blob):
    classification = classify(blob.name)
    if not classification:
        return None, "unsupported_path"
    owner_id, purpose = classification
    content_type = str(blob.content_type or mimetypes.guess_type(blob.name)[0] or "").lower()
    extension = ALLOWED_TYPES[purpose].get(content_type)
    if not extension:
        return None, "unsupported_type"
    if int(blob.size or 0) <= 0:
        return None, "empty_object"
    if int(blob.size or 0) > int(os.getenv("FINISPEAK_UPLOAD_MAX_BYTES", str(10 * 1024 * 1024))):
        return None, "oversized_object"
    return {"owner_id": owner_id, "purpose": purpose, "content_type": content_type,
            "extension": extension, "original_name": Path(blob.name).name[:255],
            "updated_at": getattr(blob, "updated", None)}, None


def finalize_references():
    rows = db.session.scalars(select(SqlStoredFile).where(
        SqlStoredFile.source_system == "firebase_storage", SqlStoredFile.deleted_at.is_(None)
    ).order_by(SqlStoredFile.created_at, SqlStoredFile.id)).all()
    grouped = {}
    for row in rows: grouped.setdefault(row.owner_id, []).append(row)
    updated = 0
    for owner_id, files in grouped.items():
        profile = db.session.get(SqlTranslator, owner_id)
        private = db.session.get(SqlInterpreterPrivate, owner_id)
        photos = [row for row in files if row.purpose == "profile_photo"]
        credentials = [row for row in files if row.purpose == "credential"]
        if profile and photos:
            profile.photo_url = serialize_file(photos[-1])["path"]; updated += 1
        if private and credentials:
            private.credential_documents = [serialize_file(row) for row in credentials]; updated += 1
    db.session.commit()
    return updated


def build_app():
    app = Flask("finispeak-storage-migration")
    configure_optional_mysql(app)
    if not app.config.get("MYSQL_CONFIGURED"):
        raise RuntimeError("All MYSQL_* variables are required for storage migration.")
    return app


def migrate(bucket, storage_root, apply=False, batch_size=50):
    root = Path(storage_root).expanduser().resolve()
    if apply: root.mkdir(mode=0o750, parents=True, exist_ok=True)
    report = {"source": 0, "valid": 0, "existing": 0, "missingOwner": 0,
              "invalid": 0, "committed": 0, "rolledBack": 0, "errors": 0}
    pending = []

    def flush():
        if not pending: return
        created = []
        try:
            for blob, values, source_hash in pending:
                data = blob.download_as_bytes()
                validate_file_content(values["content_type"], data)
                file_hash = hashlib.sha256(data).hexdigest()
                file_id = str(uuid.uuid5(NAMESPACE, source_hash))
                stored_name = f"{file_id}{values['extension']}"
                destination = (root / stored_name).resolve()
                if destination.parent != root: raise RuntimeError("Invalid target path.")
                if destination.exists():
                    if hashlib.sha256(destination.read_bytes()).hexdigest() != file_hash:
                        raise RuntimeError("Existing target content does not match source.")
                else:
                    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o640)
                    with os.fdopen(descriptor, "wb") as handle:
                        handle.write(data); handle.flush(); os.fsync(handle.fileno())
                    created.append(destination)
                db.session.add(SqlStoredFile(id=file_id, owner_id=values["owner_id"], purpose=values["purpose"],
                    original_name=values["original_name"], stored_name=stored_name,
                    content_type=values["content_type"], size_bytes=len(data), sha256=file_hash,
                    source_system="firebase_storage", source_fingerprint=source_hash,
                    metadata_json={"migrated": True}, created_at=values["updated_at"] or datetime.now(timezone.utc)))
            db.session.commit(); report["committed"] += len(pending)
        except Exception:
            db.session.rollback(); report["rolledBack"] += len(pending); report["errors"] += 1
            for path in created:
                try: path.unlink(missing_ok=True)
                except OSError: pass
            LOGGER.error("storage_migration_batch_failed records=%d", len(pending))
        finally:
            pending.clear()

    for blob in bucket.list_blobs(page_size=batch_size):
        report["source"] += 1
        values, error = validate_blob(blob)
        if error:
            report["invalid"] += 1; continue
        report["valid"] += 1
        source_hash = fingerprint(bucket.name, blob.name)
        existing = db.session.scalar(select(SqlStoredFile).where(SqlStoredFile.source_fingerprint == source_hash))
        if existing:
            try:
                data = blob.download_as_bytes()
                validate_file_content(values["content_type"], data)
                destination = (root / existing.stored_name).resolve()
                if destination.parent != root or not destination.is_file(): raise RuntimeError("Target file is missing.")
                digest = hashlib.sha256(data).hexdigest()
                if digest != existing.sha256 or digest != hashlib.sha256(destination.read_bytes()).hexdigest():
                    raise RuntimeError("Target file verification failed.")
                report["existing"] += 1
            except Exception:
                report["errors"] += 1
            continue
        if not db.session.get(SqlUser, values["owner_id"]):
            report["missingOwner"] += 1; continue
        if not apply:
            try:
                validate_file_content(values["content_type"], blob.download_as_bytes())
            except Exception:
                report["invalid"] += 1; continue
        if apply:
            pending.append((blob, values, source_hash))
            if len(pending) >= batch_size: flush()
    flush()
    report["referencesUpdated"] = 0
    if apply and not any(report[key] for key in ("invalid", "missingOwner", "errors", "rolledBack")):
        report["referencesUpdated"] = finalize_references()
    report["verified"] = report["existing"] + report["committed"]
    report["partial"] = bool(report["committed"] and (report["errors"] or report["invalid"] or report["missingOwner"]))
    return report


def main():
    parser = argparse.ArgumentParser(description="Dry-run or copy Firebase Storage into private local storage.")
    parser.add_argument("--apply", action="store_true", help="Perform writes; default is validation-only dry-run")
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--json-report", action="store_true", help="Print a machine-readable aggregate report")
    args = parser.parse_args()
    if not 1 <= args.batch_size <= 500: parser.error("--batch-size must be between 1 and 500")
    from services.firebase_service import get_db
    from firebase_admin import storage
    get_db()
    bucket_name = os.getenv("FIREBASE_STORAGE_BUCKET", "").strip()
    target_root = os.getenv("FINISPEAK_STORAGE_ROOT", "").strip()
    if not bucket_name or not target_root: raise SystemExit("FIREBASE_STORAGE_BUCKET and FINISPEAK_STORAGE_ROOT are required.")
    app = build_app()
    with app.app_context():
        report = migrate(storage.bucket(bucket_name), target_root, apply=args.apply, batch_size=args.batch_size)
    LOGGER.info("storage_migration_complete dry_run=%s source=%d valid=%d existing=%d missing_owner=%d invalid=%d committed=%d rolled_back=%d errors=%d references_updated=%d partial=%s",
        not args.apply, report["source"], report["valid"], report["existing"], report["missingOwner"],
        report["invalid"], report["committed"], report["rolledBack"], report["errors"], report["referencesUpdated"], report["partial"])
    if args.json_report:
        print(json.dumps({"dryRun": not args.apply, **report}, sort_keys=True))
    if report["errors"] or report["missingOwner"] or report["invalid"]: raise SystemExit(1)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    main()
