from dataclasses import dataclass

from models.api_key import ApiKeyModel


@dataclass
class ApiAccessError(RuntimeError):
    message: str
    status_code: int
    retry_after: int | None = None

    def __str__(self):
        return self.message


def authenticate_api_request(request, required_scopes=()):
    token = request.headers.get("X-API-Key", "").strip()
    if not token:
        scheme, _, bearer = request.headers.get("Authorization", "").partition(" ")
        if scheme.lower() == "bearer" and bearer.startswith("fs_live_"):
            token = bearer.strip()
    if not token:
        raise ApiAccessError("A FiniSpeak API key is required.", 401)
    try:
        api_key = ApiKeyModel.authenticate(token)
    except RuntimeError as exc:
        raise ApiAccessError(str(exc), 503) from exc
    if not api_key:
        raise ApiAccessError("The API key is invalid, expired, or revoked.", 401)
    missing = set(required_scopes) - set(api_key.get("scopes") or [])
    if missing:
        raise ApiAccessError(f"The API key is missing required scope: {sorted(missing)[0]}.", 403)
    try:
        quota = ApiKeyModel.consume_quota(api_key)
    except Exception as exc:
        raise ApiAccessError("API quota enforcement is temporarily unavailable.", 503) from exc
    if not quota.get("allowed"):
        if quota.get("reason") == "daily_quota":
            raise ApiAccessError("The API key's daily quota has been exhausted.", 429, 3600)
        raise ApiAccessError("The API key's per-minute rate limit has been reached.", 429, 60)
    return api_key, quota
