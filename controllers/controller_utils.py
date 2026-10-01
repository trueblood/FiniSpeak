from flask import jsonify, request

from services.auth_service import (
    AuthenticationError,
    AuthorizationError,
    authenticate_request,
    require_admin,
)


def identity_or_response(admin=False):
    try:
        identity = authenticate_request(request)
        return (require_admin(identity) if admin else identity), None
    except AuthenticationError as exc:
        return None, (jsonify({"error": str(exc)}), 401)
    except AuthorizationError as exc:
        return None, (jsonify({"error": str(exc)}), 403)


def json_body():
    return request.get_json(silent=True) or {}
