"""Private, authorization-aware local object storage."""

import hashlib
import os
import uuid
import re
from datetime import datetime, timezone
from pathlib import Path

from flask import current_app
from werkzeug.utils import secure_filename

from extensions import db
from models.sql_models import SqlStoredFile


ALLOWED_TYPES = {
    "credential": {"application/pdf": ".pdf", "image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"},
    "profile_photo": {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"},
}


def validate_file_content(content_type, data):
    signatures = {
        "application/pdf": lambda value: value.startswith(b"%PDF-"),
        "image/jpeg": lambda value: value.startswith(b"\xff\xd8\xff"),
        "image/png": lambda value: value.startswith(b"\x89PNG\r\n\x1a\n"),
        "image/webp": lambda value: len(value) >= 12 and value.startswith(b"RIFF") and value[8:12] == b"WEBP",
    }
    validator = signatures.get(content_type)
    if not validator or not validator(data):
        raise ValueError("File content does not match its declared type.")


def storage_root():
    configured = os.getenv("FINISPEAK_STORAGE_ROOT", "").strip()
    if not configured:
        if current_app.testing:
            configured = current_app.config.get("TEST_STORAGE_ROOT", "/tmp/finispeak-test-storage")
        else:
            raise RuntimeError("FINISPEAK_STORAGE_ROOT is required.")
    root = Path(configured).expanduser().resolve()
    public_root = Path(current_app.static_folder).resolve()
    if root == public_root or public_root in root.parents:
        raise RuntimeError("Private storage must be outside the public static directory.")
    root.mkdir(mode=0o750, parents=True, exist_ok=True)
    return root


def save_upload(upload, owner_id, purpose):
    if purpose not in ALLOWED_TYPES:
        raise ValueError("Unsupported file purpose.")
    content_type = str(upload.mimetype or "").lower()
    extension = ALLOWED_TYPES[purpose].get(content_type)
    if not extension:
        raise ValueError("Unsupported file type.")
    maximum = int(os.getenv("FINISPEAK_UPLOAD_MAX_BYTES", str(10 * 1024 * 1024)))
    data = upload.stream.read(maximum + 1)
    if not data or len(data) > maximum:
        raise ValueError(f"Files must be between 1 byte and {maximum} bytes.")
    validate_file_content(content_type, data)
    file_id, now = str(uuid.uuid4()), datetime.now(timezone.utc)
    stored_name = f"{file_id}{extension}"
    destination = storage_root() / stored_name
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o640)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data); handle.flush(); os.fsync(handle.fileno())
        row = SqlStoredFile(id=file_id, owner_id=owner_id, purpose=purpose,
            original_name=secure_filename(upload.filename or f"upload{extension}")[:255] or f"upload{extension}",
            stored_name=stored_name, content_type=content_type, size_bytes=len(data),
            sha256=hashlib.sha256(data).hexdigest(), metadata_json={}, created_at=now)
        db.session.add(row); db.session.commit()
        return serialize_file(row)
    except Exception:
        db.session.rollback()
        try: destination.unlink(missing_ok=True)
        except OSError: pass
        raise


def serialize_file(row):
    return {"id": row.id, "name": row.original_name, "contentType": row.content_type,
        "size": row.size_bytes, "purpose": row.purpose, "path": f"/api/files/{row.id}/content",
        "uploadedAt": row.created_at.isoformat() if row.created_at else None}


def authorize_file(row, identity):
    if not row or row.deleted_at:
        return False
    if row.purpose == "profile_photo":
        return bool(identity)
    return identity.get("role") == "admin" or identity.get("uid") == row.owner_id


def validate_profile_file_references(owner_id, public, private):
    """Reject forged, cross-account, deleted, and non-local file references."""
    references = []
    photo_url = str(public.get("photoUrl") or "").strip()
    if photo_url: references.append((photo_url, "profile_photo"))
    documents = private.get("credentialDocuments", [])
    if not isinstance(documents, list) or len(documents) > 20:
        raise ValueError("Credential documents must be a list of at most 20 files.")
    for document in documents:
        if not isinstance(document, dict): raise ValueError("Invalid credential file reference.")
        references.append((str(document.get("path") or ""), "credential"))
    for path, purpose in references:
        match = re.fullmatch(r"/api/files/([0-9a-f-]{36})/content", path)
        row = db.session.get(SqlStoredFile, match.group(1)) if match else None
        if not row or row.deleted_at or row.owner_id != owner_id or row.purpose != purpose:
            raise ValueError("Invalid or unauthorized file reference.")


def file_path(row):
    path = (storage_root() / row.stored_name).resolve()
    if path.parent != storage_root():
        raise RuntimeError("Stored file path is invalid.")
    return path


def delete_file(row):
    row.deleted_at = datetime.now(timezone.utc); db.session.commit()
    try: file_path(row).unlink(missing_ok=True)
    except OSError: current_app.logger.warning("stored_file_cleanup_failed file_id=%s", row.id)
