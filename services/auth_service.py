"""First-party MySQL authentication, sessions, and account recovery."""

import hashlib
import hmac
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from flask import current_app
from flask_jwt_extended import create_access_token, get_jwt, get_jwt_identity, verify_jwt_in_request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from extensions import db
from models.sql_models import SqlAuthCredential, SqlAuthRateLimit, SqlAuthSession, SqlAuthToken, SqlUser
from repositories.normalization import canonicalize_phone, normalize_email, normalize_phone


PASSWORD_HASHER = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4, hash_len=32, salt_len=16)
TOKEN_PURPOSES = {"verify_email": 24 * 60, "reset_password": 30}


class AuthenticationError(RuntimeError):
    pass


class AuthorizationError(RuntimeError):
    pass


class RateLimitError(RuntimeError):
    pass


def test_email_verification_bypass_enabled():
    """Disable email verification only for the explicit IP-based test deployment."""
    return os.getenv("FINISPEAK_TEST_DEPLOYMENT", "").strip().lower() == "true"


def _now():
    return datetime.now(timezone.utc)


def _aware(value):
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=timezone.utc)


def _password_valid(password):
    value = str(password or "")
    return 12 <= len(value) <= 256 and any(c.isalpha() for c in value) and any(c.isdigit() for c in value)


def _profile(user):
    return {"uid": user.id, "email": user.email, "displayName": user.display_name or user.email,
            "role": user.role or "customer", "status": user.status or "active"}


def _token_hash(token):
    return hashlib.sha256(str(token).encode("utf-8")).hexdigest()


def enforce_rate_limit(scope, discriminator, limit, window_minutes=15, block_minutes=15):
    """Apply a database-backed limit without storing the identifying value."""
    now = _now()
    secret = str(current_app.config["JWT_SECRET_KEY"]).encode()
    key_hash = hmac.new(secret, str(discriminator or "unknown").casefold().encode(), hashlib.sha256).hexdigest()
    row = db.session.scalar(select(SqlAuthRateLimit).where(
        SqlAuthRateLimit.scope == scope, SqlAuthRateLimit.key_hash == key_hash).with_for_update())
    if row and row.blocked_until and _aware(row.blocked_until) > now:
        db.session.rollback()
        raise RateLimitError("Too many requests. Try again later.")
    created = not row
    if created:
        row = SqlAuthRateLimit(scope=scope, key_hash=key_hash, window_started_at=now,
            attempts=0, updated_at=now); db.session.add(row)
    elif (_aware(row.window_started_at) + timedelta(minutes=window_minutes)) <= now:
        row.window_started_at, row.attempts, row.blocked_until = now, 0, None
    row.attempts = int(row.attempts or 0) + 1; row.updated_at = now
    if row.attempts > limit:
        row.blocked_until = now + timedelta(minutes=block_minutes)
        db.session.commit()
        raise RateLimitError("Too many requests. Try again later.")
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        if not created: raise
        # A concurrent worker created the same limiter row. Lock and apply this
        # request to that row so the collision cannot bypass the shared limit.
        row = db.session.scalar(select(SqlAuthRateLimit).where(
            SqlAuthRateLimit.scope == scope, SqlAuthRateLimit.key_hash == key_hash).with_for_update())
        if not row: raise
        if row.blocked_until and _aware(row.blocked_until) > now:
            db.session.rollback()
            raise RateLimitError("Too many requests. Try again later.")
        if (_aware(row.window_started_at) + timedelta(minutes=window_minutes)) <= now:
            row.window_started_at, row.attempts, row.blocked_until = now, 0, None
        row.attempts = int(row.attempts or 0) + 1; row.updated_at = now
        blocked = row.attempts > limit
        if blocked: row.blocked_until = now + timedelta(minutes=block_minutes)
        db.session.commit()
        if blocked: raise RateLimitError("Too many requests. Try again later.")


def register_account(email, password, display_name, phone="", role="customer"):
    email, display_name = normalize_email(email), str(display_name or "").strip()
    role = "translator_applicant" if role == "translator" else "customer"
    if not email or len(email) > 320 or "@" not in email:
        raise ValueError("A valid email address is required.")
    if not display_name or len(display_name) > 160:
        raise ValueError("A valid display name is required.")
    if not _password_valid(password):
        raise ValueError("Password must be 12–256 characters and contain letters and numbers.")
    canonical_phone = canonicalize_phone(phone)
    if phone and not canonical_phone:
        raise ValueError("Enter a valid phone number including its country code.")
    phone_normalized = normalize_phone(canonical_phone)
    existing = db.session.scalar(select(SqlUser).where(SqlUser.email_normalized == email).limit(1))
    if existing:
        if db.session.get(SqlAuthCredential, existing.id):
            raise ValueError("An account with that email already exists.")
        raise ValueError("This migrated account must be activated through password reset.")
    if phone_normalized and db.session.scalar(select(SqlUser.id).where(SqlUser.phone_normalized == phone_normalized).limit(1)):
        raise ValueError("That phone number is already connected to another FiniSpeak account.")
    now, user_id = _now(), uuid.uuid4().hex
    raw = {"uid": user_id, "email": email, "displayName": display_name, "phone": canonical_phone,
           "phoneNormalized": phone_normalized,
           "role": role, "status": "active", "createdAt": now.isoformat(), "updatedAt": now.isoformat()}
    user = SqlUser(id=user_id, uid=user_id, display_name=display_name, email=email, email_normalized=email,
        phone=raw["phone"], phone_normalized=phone_normalized, role=role, status="active", created_at=now, updated_at=now,
        raw_document=raw, migrated_at=now, mutation_version=1)
    credential = SqlAuthCredential(user_id=user_id, email_normalized=email,
        password_hash=PASSWORD_HASHER.hash(password), password_changed_at=now, created_at=now, updated_at=now)
    try:
        # The models intentionally have no ORM relationship, so explicitly
        # flush the parent before its credential. SQLite tolerated add_all()
        # ordering, but MySQL correctly enforces the users.id foreign key at
        # statement execution time.
        db.session.add(user)
        db.session.flush()
        db.session.add(credential)
        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        raise ValueError("An account with that email already exists.") from exc
    return _profile(user), issue_action_token(user_id, "verify_email")


def authenticate_password(email, password):
    normalized = normalize_email(email)
    credential = db.session.scalar(select(SqlAuthCredential).where(
        SqlAuthCredential.email_normalized == normalized).with_for_update())
    if not credential:
        try:
            PASSWORD_HASHER.verify(PASSWORD_HASHER.hash("not-the-password-123"), str(password or ""))
        except Exception:
            pass
        raise AuthenticationError("Email or password is incorrect.")
    now = _now()
    if credential.locked_until and _aware(credential.locked_until) > now:
        raise AuthenticationError("Sign-in is temporarily locked. Try again later.")
    try:
        PASSWORD_HASHER.verify(credential.password_hash, str(password or ""))
    except (VerifyMismatchError, InvalidHashError):
        credential.failed_attempts = int(credential.failed_attempts or 0) + 1
        if credential.failed_attempts >= 8:
            credential.locked_until, credential.failed_attempts = now + timedelta(minutes=15), 0
        credential.updated_at = now; db.session.commit()
        raise AuthenticationError("Email or password is incorrect.")
    credential.failed_attempts, credential.locked_until, credential.updated_at = 0, None, now
    if not credential.email_verified_at:
        if test_email_verification_bypass_enabled():
            credential.email_verified_at = now
        else:
            db.session.commit()
            raise AuthorizationError("Verify your email before signing in.")
    if PASSWORD_HASHER.check_needs_rehash(credential.password_hash):
        credential.password_hash = PASSWORD_HASHER.hash(password)
    user = db.session.get(SqlUser, credential.user_id)
    if not user or user.status == "suspended":
        db.session.rollback(); raise AuthorizationError("This FiniSpeak account is suspended.")
    db.session.commit()
    return _profile(user), create_session(user)


def create_session(user):
    now = _now(); hours = min(max(int(os.getenv("FINISPEAK_SESSION_HOURS", "12")), 1), 168)
    session_id, expires = str(uuid.uuid4()), now + timedelta(hours=hours)
    db.session.add(SqlAuthSession(id=session_id, user_id=user.id, expires_at=expires,
        created_at=now, last_seen_at=now)); db.session.commit()
    token = create_access_token(identity=user.id, additional_claims={"sid": session_id,
        "role": user.role or "customer", "email": user.email}, expires_delta=timedelta(hours=hours))
    return {"accessToken": token, "expiresAt": expires.isoformat(), "sessionId": session_id}


def issue_action_token(user_id, purpose):
    if purpose not in TOKEN_PURPOSES:
        raise ValueError("Unsupported authentication token purpose.")
    now, raw = _now(), secrets.token_urlsafe(32)
    db.session.query(SqlAuthToken).filter_by(user_id=user_id, purpose=purpose, used_at=None).update({"used_at": now})
    db.session.add(SqlAuthToken(id=str(uuid.uuid4()), user_id=user_id, purpose=purpose,
        token_hash=_token_hash(raw), expires_at=now + timedelta(minutes=TOKEN_PURPOSES[purpose]), created_at=now))
    db.session.commit()
    return raw


def request_password_reset(email):
    user = db.session.scalar(select(SqlUser).where(SqlUser.email_normalized == normalize_email(email)).limit(1))
    return (user, issue_action_token(user.id, "reset_password")) if user else (None, None)


def set_test_account_password(user_id, password):
    """Activate or reset one account from a trusted server-side operator session."""
    if not test_email_verification_bypass_enabled():
        raise AuthorizationError("The test-deployment email bypass is not enabled.")
    if not _password_valid(password):
        raise ValueError("Password must be 12–256 characters and contain letters and numbers.")
    user = db.session.get(SqlUser, str(user_id or "").strip())
    if not user:
        raise AuthenticationError("The requested account does not exist.")
    token = issue_action_token(user.id, "reset_password")
    return consume_action_token(token, "reset_password", password)


def consume_action_token(raw_token, purpose, password=None):
    now = _now()
    row = db.session.scalar(select(SqlAuthToken).where(SqlAuthToken.token_hash == _token_hash(raw_token),
        SqlAuthToken.purpose == purpose).with_for_update())
    if not row or row.used_at or _aware(row.expires_at) <= now:
        raise AuthenticationError("This token is invalid or expired.")
    credential, user = db.session.get(SqlAuthCredential, row.user_id), db.session.get(SqlUser, row.user_id)
    if purpose == "verify_email":
        if not credential: raise AuthenticationError("Account credentials are unavailable.")
        credential.email_verified_at, credential.updated_at = now, now
    elif purpose == "reset_password":
        if not _password_valid(password):
            raise ValueError("Password must be 12–256 characters and contain letters and numbers.")
        if credential:
            credential.password_hash, credential.password_changed_at, credential.updated_at = PASSWORD_HASHER.hash(password), now, now
            credential.failed_attempts, credential.locked_until = 0, None
            credential.email_verified_at = now
        else:
            if not user or not user.email_normalized: raise AuthenticationError("Account cannot be activated.")
            db.session.add(SqlAuthCredential(user_id=user.id, email_normalized=user.email_normalized,
                password_hash=PASSWORD_HASHER.hash(password), email_verified_at=now,
                password_changed_at=now, created_at=now, updated_at=now))
        db.session.query(SqlAuthSession).filter_by(user_id=row.user_id, revoked_at=None).update({"revoked_at": now})
    row.used_at = now; db.session.commit()
    return _profile(user)


def authenticate_request(_request=None, optional=False):
    try:
        verify_jwt_in_request(optional=optional, locations=["headers", "cookies"])
    except Exception as exc:
        raise AuthenticationError("A valid FiniSpeak session is required.") from exc
    user_id = get_jwt_identity()
    if not user_id:
        if optional: return None
        raise AuthenticationError("A valid FiniSpeak session is required.")
    claims, now = get_jwt(), _now()
    session = db.session.get(SqlAuthSession, claims.get("sid"))
    if not session or session.user_id != user_id or session.revoked_at or _aware(session.expires_at) <= now:
        raise AuthenticationError("The FiniSpeak session is invalid or expired.")
    user = db.session.get(SqlUser, user_id)
    if not user: raise AuthenticationError("The FiniSpeak account no longer exists.")
    if user.status == "suspended": raise AuthorizationError("This FiniSpeak account is suspended.")
    session.last_seen_at = now; db.session.commit()
    identity = _profile(user); identity["claims"] = claims
    return identity


def revoke_current_session():
    session = db.session.get(SqlAuthSession, get_jwt().get("sid"))
    if session and not session.revoked_at:
        session.revoked_at = _now(); db.session.commit()


def require_admin(identity):
    if identity.get("role") != "admin":
        raise AuthorizationError("Administrator access is required.")
    return identity
