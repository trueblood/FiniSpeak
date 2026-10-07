from flask import jsonify, request

from controllers.controller_utils import identity_or_response, json_body
from models.account import AccountModel
from models.review import ReviewModel
from models.translator import TranslatorModel
from models.api_key import ApiKeyModel
from services.language_monitoring_service import language_metrics_summary
from services.firebase_service import get_db


def overview():
    _, error = identity_or_response(admin=True)
    if error:
        return error
    db = get_db()
    accounts = AccountModel.all()
    interpreters = [doc.to_dict() for doc in db.collection("translators").stream()]
    calls = [doc.to_dict() for doc in db.collection("calls").stream()]
    organizations = [doc.to_dict() for doc in db.collection("organizations").stream()]
    return jsonify({"metrics": {
        "accounts": len(accounts), "activeAccounts": sum(account.get("status", "active") == "active" for account in accounts),
        "verifiedInterpreters": sum(profile.get("verificationStatus") == "verified" for profile in interpreters),
        "pendingVerifications": len(TranslatorModel.pending_verification()), "sessions": len(calls),
        "activeSessions": sum(call.get("status") in {"ringing", "connected", "active"} for call in calls),
        "organizations": len(organizations),
    }})


def verifications():
    _, error = identity_or_response(admin=True)
    if error:
        return error
    return jsonify({"interpreters": TranslatorModel.pending_verification()})


def activity():
    _, error = identity_or_response(admin=True)
    if error:
        return error
    db = get_db()
    accounts = AccountModel.all()
    sessions = [{"id": doc.id, **doc.to_dict()} for doc in db.collection("calls").stream()]
    organizations = [{"id": doc.id, **doc.to_dict()} for doc in db.collection("organizations").stream()]
    reviews = []
    for interpreter in db.collection("translators").stream():
        for review in interpreter.reference.collection("reviews").stream():
            reviews.append({"id": review.id, "interpreterId": interpreter.id, **review.to_dict()})

    def newest(items):
        return sorted(items, key=lambda item: str(item.get("createdAt") or item.get("updatedAt") or ""), reverse=True)[:100]

    return jsonify({
        "accounts": newest(accounts),
        "sessions": newest(sessions),
        "organizations": newest(organizations),
        "reviews": newest(reviews),
    })


def verify_interpreter(translator_id):
    identity, error = identity_or_response(admin=True)
    if error:
        return error
    data = json_body()
    try:
        profile = TranslatorModel.set_verification(translator_id, data.get("status"), identity["uid"], str(data.get("notes") or ""))
        return (jsonify({"profile": profile}), 200) if profile else (jsonify({"error": "Interpreter not found"}), 404)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


def moderate_review(interpreter_id, review_id):
    _, error = identity_or_response(admin=True)
    if error:
        return error
    try:
        review = ReviewModel.moderate(interpreter_id, review_id, json_body().get("status"))
        return (jsonify({"review": review}), 200) if review else (jsonify({"error": "Review not found"}), 404)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


def api_keys():
    identity, error = identity_or_response(admin=True)
    if error:
        return error
    if request.method == "POST":
        try:
            return jsonify({"apiKey": ApiKeyModel.create(json_body(), identity["uid"])}), 201
        except (RuntimeError, ValueError) as exc:
            return jsonify({"error": str(exc)}), 400
    return jsonify({"apiKeys": ApiKeyModel.all()})


def revoke_api_key(key_id):
    identity, error = identity_or_response(admin=True)
    if error:
        return error
    api_key = ApiKeyModel.revoke(key_id, identity["uid"])
    return (jsonify({"apiKey": api_key}), 200) if api_key else (jsonify({"error": "API key not found."}), 404)


def api_usage():
    _, error = identity_or_response(admin=True)
    if error:
        return error
    return jsonify(ApiKeyModel.usage_summary())


def language_metrics():
    _, error = identity_or_response(admin=True)
    if error:
        return error
    return jsonify(language_metrics_summary())
