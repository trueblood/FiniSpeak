"""Firebase bearer-token authentication and role checks for reusable APIs."""

from firebase_admin import auth as firebase_auth

from services.firebase_service import get_db


class AuthenticationError(RuntimeError):
    pass


class AuthorizationError(RuntimeError):
    pass


def authenticate_request(request):
    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise AuthenticationError("A Firebase bearer token is required.")

    # get_db initializes Firebase Admin with either the configured service
    # account or the Cloud Run application-default identity.
    get_db()
    try:
        decoded = firebase_auth.verify_id_token(token.strip())
    except Exception as exc:
        raise AuthenticationError("The Firebase ID token is invalid or expired.") from exc

    uid = decoded.get("uid")
    if not uid:
        raise AuthenticationError("The Firebase ID token has no user ID.")

    user_document = get_db().collection("users").document(uid).get()
    profile = user_document.to_dict() if user_document.exists else {}
    role = "admin" if decoded.get("admin") is True else profile.get("role", "customer")
    if role != "admin" and profile.get("status", "active") == "suspended":
        raise AuthorizationError("This FiniSpeak account is suspended.")
    return {
        "uid": uid,
        "email": decoded.get("email") or profile.get("email"),
        "displayName": profile.get("displayName") or decoded.get("name") or decoded.get("email"),
        "role": role,
        "claims": decoded,
    }


def require_admin(identity):
    if identity.get("role") != "admin":
        raise AuthorizationError("Administrator access is required.")
    return identity
