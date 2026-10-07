from flask import g, jsonify, request

from services.auth_service import (
    AuthenticationError,
    AuthorizationError,
    authenticate_request,
    require_admin,
)
from services.api_access_service import ApiAccessError, authenticate_api_request


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


def api_identity_or_response(*required_scopes):
    try:
        api_key, quota = authenticate_api_request(request, required_scopes)
        g.api_client = api_key
        g.api_quota = quota
        return {
            "uid": f"api:{api_key['id']}",
            "role": "api_client",
            "organizationId": api_key.get("organizationId"),
            "scopes": api_key.get("scopes", []),
        }, None
    except ApiAccessError as exc:
        response = jsonify({"error": str(exc)})
        response.status_code = exc.status_code
        if exc.retry_after:
            response.headers["Retry-After"] = str(exc.retry_after)
        return None, response
