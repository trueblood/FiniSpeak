from flask import jsonify

from controllers.controller_utils import identity_or_response, json_body
from repositories.provider import repository_proxy
from services.file_storage_service import validate_profile_file_references

TranslatorModel = repository_proxy("translators")


def index():
    try:
        return jsonify(TranslatorModel.all_public())
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 503


def detail(translator_id):
    try:
        profile = TranslatorModel.get(translator_id)
        return (jsonify(profile), 200) if profile else (jsonify({"error": "Interpreter not found"}), 404)
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 503


def current_private():
    identity, error = identity_or_response()
    if error:
        return error
    public = TranslatorModel.get(identity["uid"], public=False)
    if not public:
        return jsonify({"error": "Interpreter profile not found"}), 404
    return jsonify({"profile": public, "private": TranslatorModel.get_private(identity["uid"])})


def save_current():
    identity, error = identity_or_response()
    if error:
        return error
    if identity.get("role") != "admin" and not TranslatorModel.get(identity["uid"], public=False):
        return jsonify({"error": "An interpreter account is required."}), 403
    data = json_body(); public = data.get("profile") or {}; private = data.get("private") or {}
    allowed_public = {"displayName", "bio", "languages", "dialects", "specialties", "credentials", "yearsExperience", "availability", "photoUrl", "serviceLocation", "serviceOptions", "credentialStatus", "onboardingStatus"}
    allowed_private = {"email", "phone", "credentialDocuments"}
    public = {key: value for key, value in public.items() if key in allowed_public}
    private = {key: value for key, value in private.items() if key in allowed_private}
    if not str(public.get("displayName") or "").strip():
        return jsonify({"error": "displayName is required"}), 400
    try:
        validate_profile_file_references(identity["uid"], public, private)
        saved = TranslatorModel.save_profile(identity["uid"], public, private)
        return jsonify(saved)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


def enroll():
    identity, error = identity_or_response()
    if error:
        return error
    data = json_body()
    try:
        profile = TranslatorModel.enroll(identity, str(data.get("phone") or "").strip())
        return jsonify({"profile": profile}), 201
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
