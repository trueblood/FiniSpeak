from flask import jsonify, request

from controllers.controller_utils import identity_or_response, json_body
from models.account import AccountModel


def current():
    identity, error = identity_or_response()
    if error:
        return error
    account = AccountModel.get(identity["uid"]) or identity
    return jsonify({"account": account})


def list_accounts():
    _, error = identity_or_response(admin=True)
    if error:
        return error
    return jsonify({"accounts": AccountModel.all()})


def lookup():
    _, error = identity_or_response()
    if error:
        return error
    account = AccountModel.find_by_email(request.args.get("email"))
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
    account = AccountModel.update_status(uid, status)
    return (jsonify({"account": account}), 200) if account else (jsonify({"error": "Account not found"}), 404)
