from flask import jsonify, request, send_file

from controllers.controller_utils import identity_or_response
from extensions import db
from models.sql_models import SqlStoredFile
from services.file_storage_service import authorize_file, delete_file, file_path, save_upload


def upload():
    identity, error = identity_or_response()
    if error: return error
    uploaded = request.files.get("file")
    if not uploaded: return jsonify({"error": "A file upload is required."}), 400
    try:
        record = save_upload(uploaded, identity["uid"], request.form.get("purpose", "credential"))
        return jsonify({"file": record}), 201
    except (ValueError, RuntimeError) as exc:
        return jsonify({"error": str(exc)}), 400


def content(file_id):
    identity, error = identity_or_response()
    if error: return error
    row = db.session.get(SqlStoredFile, file_id)
    if not authorize_file(row, identity): return jsonify({"error": "File not found or access denied."}), 404
    path = file_path(row)
    if not path.is_file(): return jsonify({"error": "Stored file is unavailable."}), 404
    return send_file(path, mimetype=row.content_type, download_name=row.original_name,
        as_attachment=request.args.get("download") == "1", conditional=True, max_age=0)


def remove(file_id):
    identity, error = identity_or_response()
    if error: return error
    row = db.session.get(SqlStoredFile, file_id)
    if not row or row.deleted_at or (identity.get("role") != "admin" and row.owner_id != identity["uid"]):
        return jsonify({"error": "File not found or access denied."}), 404
    delete_file(row)
    return "", 204
