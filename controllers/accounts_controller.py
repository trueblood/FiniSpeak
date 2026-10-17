from flask import jsonify, request

from controllers.controller_utils import identity_or_response, json_body
from repositories.provider import repository_proxy

AccountModel = repository_proxy("accounts")


def current():
    identity, error = identity_or_response()
    if error:
        return error
    account = AccountModel.get(identity["uid"]) or identity
    return jsonify({"account": account})


def bootstrap():
    identity, error = identity_or_response()
    if error:
        return error
    data = json_body()
    display_name = str(data.get("displayName") or identity.get("displayName") or "").strip()
    phone = str(data.get("phone") or "").strip()
    if not display_name or len(display_name) > 160:
        return jsonify({"error": "A valid displayName is required"}), 400
    try:
        account = AccountModel.bootstrap(identity, {"displayName": display_name, "phone": phone})
        return jsonify({"account": account}), 200
    except (ValueError, RuntimeError) as exc:
        return jsonify({"error": str(exc)}), 400


def update_current():
    identity, error = identity_or_response()
    if error:
        return error
    data = json_body()
    display_name = str(data.get("displayName") or "").strip()
    phone = str(data.get("phone") or "").strip()
    if not display_name or len(display_name) > 160 or len(phone) > 64:
        return jsonify({"error": "A valid displayName and phone are required"}), 400
    try:
        account = AccountModel.update_profile(identity["uid"], {"displayName": display_name, "phone": phone})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return (jsonify({"account": account}), 200) if account else (jsonify({"error": "Account not found"}), 404)


def list_accounts():
    _, error = identity_or_response(admin=True)
    if error:
        return error
    return jsonify({"accounts": AccountModel.all()})


def lookup():
    _, error = identity_or_response()
    if error:
        return error
    email = request.args.get("email")
    phone = request.args.get("phone")
    if not email and not phone:
        return jsonify({"error": "email or phone is required"}), 400
    account = AccountModel.find_by_email(email) if email else AccountModel.find_by_phone(phone)
    if not account or account.get("status") != "active":
        return jsonify({"error": "Account not found"}), 404
    return jsonify({"account": account})


def update_status(uid):
    _, error = identity_or_response(admin=True)
    if error:
        return error
    status = json_body().get("status")
    if status not in {"active", "pending", "suspended"}:
        return jsonify({"error": "status must be active, pending, or suspended"}), 400
    try:
        account = AccountModel.update_status(uid, status)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return (jsonify({"account": account}), 200) if account else (jsonify({"error": "Account not found"}), 404)
