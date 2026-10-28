from flask import current_app, jsonify, request
from flask_jwt_extended import set_access_cookies, unset_jwt_cookies

from controllers.controller_utils import identity_or_response, json_body
from services.auth_service import (
    AuthenticationError, AuthorizationError, RateLimitError, authenticate_password, authenticate_request,
    consume_action_token, enforce_rate_limit, local_development_sign_in_enabled, register_account,
    request_password_reset, revoke_current_session, test_email_verification_bypass_enabled,
)
from services.email_service import send_account_link
from repositories.provider import get_repository


def _session_response(user, session):
    response = jsonify({"user": user, **session})
    set_access_cookies(response, session["accessToken"])
    return response


def register():
    data = json_body()
    try:
        enforce_rate_limit("register", f"{request.remote_addr}:{data.get('email', '')}", 5, 30, 30)
        user, verification_token = register_account(data.get("email"), data.get("password"),
            data.get("displayName"), data.get("phone"), data.get("role"))
        if data.get("role") == "translator":
            get_repository("translators").enroll(user, str(data.get("phone") or "").strip())
        if test_email_verification_bypass_enabled() or local_development_sign_in_enabled():
            consume_action_token(verification_token, "verify_email")
            return jsonify({
                "message": "Account created. You can sign in now.",
                "user": user,
            }), 201
        send_account_link(user["email"], "Verify your FiniSpeak email", "/verify-email", verification_token)
        payload = {"message": "Check your email to verify the account.", "user": user}
        if current_app.testing:
            payload["testToken"] = verification_token
        return jsonify(payload), 201
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except RateLimitError as exc:
        return jsonify({"error": str(exc)}), 429
    except RuntimeError:
        current_app.logger.error("account_email_delivery_failed type=verification")
        return jsonify({"error": "The account was created, but verification email delivery failed. Use password recovery after email is configured."}), 503


def login():
    data = json_body()
    try:
        enforce_rate_limit("login", f"{request.remote_addr}:{data.get('email', '')}", 20, 15, 15)
        user, session = authenticate_password(data.get("email"), data.get("password"))
        return _session_response(user, session)
    except AuthenticationError as exc:
        return jsonify({"error": str(exc)}), 401
    except AuthorizationError as exc:
        return jsonify({"error": str(exc)}), 403
    except RateLimitError as exc:
        return jsonify({"error": str(exc)}), 429


def logout():
    _, error = identity_or_response()
    if error: return error
    revoke_current_session()
    response = jsonify({"message": "Signed out."}); unset_jwt_cookies(response)
    return response


def session():
    try:
        identity = authenticate_request(request)
        return jsonify({"user": {key: identity.get(key) for key in ("uid", "email", "displayName", "role", "status")}})
    except AuthenticationError as exc:
        return jsonify({"error": str(exc)}), 401
    except AuthorizationError as exc:
        return jsonify({"error": str(exc)}), 403


def forgot_password():
    data = json_body()
    try:
        enforce_rate_limit("password_reset", f"{request.remote_addr}:{data.get('email', '')}", 5, 30, 30)
    except RateLimitError as exc:
        return jsonify({"error": str(exc)}), 429
    user, token = request_password_reset(data.get("email"))
    if user and token:
        try:
            send_account_link(user.email, "Reset your FiniSpeak password", "/reset-password", token)
        except RuntimeError:
            current_app.logger.error("account_email_delivery_failed type=password_reset")
            if current_app.testing:
                return jsonify({"message": "If the account exists, a recovery link was created.", "testToken": token})
    return jsonify({"message": "If the account exists, a recovery link will be sent."})


def reset_password():
    data = json_body()
    try:
        consume_action_token(data.get("token"), "reset_password", data.get("password"))
        return jsonify({"message": "Password updated. Sign in with the new password."})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except AuthenticationError as exc:
        return jsonify({"error": str(exc)}), 401


def verify_email():
    try:
        consume_action_token(json_body().get("token"), "verify_email")
        return jsonify({"message": "Email verified. You can sign in."})
    except AuthenticationError as exc:
        return jsonify({"error": str(exc)}), 401
