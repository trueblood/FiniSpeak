"""MySQL repository implementations for the Phase 1 cutover seam.

These classes are not selected by controllers yet.  They accept an explicit
SQLAlchemy Session, which keeps initialization and transaction ownership
testable and prevents importing this module from opening a database connection.
"""

import hashlib
import hmac
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select
from models.account import normalize_phone
from models.call import CallModel
from models.sql_models import (
    SqlApiKey, SqlApiUsageCounter, SqlApiUsageEvent, SqlCall,
    SqlInterpreterPrivate, SqlLanguageDetectionMetric, SqlOrganization,
    SqlParticipant, SqlReferenceDialect, SqlReferenceLanguage,
    SqlReferenceSpecialty, SqlReview, SqlTranscript, SqlTranslator, SqlUser,
)
from repositories.normalization import normalize_email
from services.geo_service import haversine_miles, validate_coordinates


def _now():
    return datetime.now(timezone.utc)


def _new_id():
    return uuid.uuid4().hex


def _raw(row):
    return dict(row.raw_document or {})


def _document(row, fields, identifier=None):
    data = _raw(row)
    for api_name, column_name in fields.items():
        value = getattr(row, column_name)
        if value is not None or api_name in data:
            data[api_name] = value
    data[identifier or "id"] = row.id
    return data


def _touch(row, changes, fields):
    raw = _raw(row)
    raw.update(changes)
    row.raw_document = raw
    for api_name, value in changes.items():
        column_name = fields.get(api_name)
        if column_name:
            setattr(row, column_name, value)
    row.mutation_version = int(row.mutation_version or 0) + 1
    row.source_updated_at = changes.get("updatedAt", _now())
    row.last_mutation_id = uuid.uuid4().hex


def _commit(session):
    try:
        session.commit()
    except Exception:
        session.rollback()
        raise


ACCOUNT_FIELDS = {
    "uid": "uid", "displayName": "display_name", "email": "email", "phone": "phone",
    "phoneNormalized": "phone_normalized", "role": "role", "status": "status",
    "createdAt": "created_at", "updatedAt": "updated_at",
}
CALL_FIELDS = {
    "callerId": "caller_id", "callerName": "caller_name", "receiverId": "receiver_id",
    "receiverName": "receiver_name", "translatorId": "translator_id", "translatorName": "translator_name",
    "status": "status", "translationStatus": "translation_status", "language": "language",
    "detectedLanguage": "detected_language", "detectedLanguageConfidence": "detected_language_confidence",
    "requestedLanguages": "requested_languages", "dialect": "dialect", "specialty": "specialty",
    "purpose": "purpose", "recommendedTranslatorIds": "recommended_translator_ids",
    "routingStatus": "routing_status", "scheduledAt": "scheduled_at", "createdAt": "created_at",
    "updatedAt": "updated_at", "startedAt": "started_at", "endedAt": "ended_at",
}
TRANSLATOR_FIELDS = {
    "uid": "uid", "displayName": "display_name", "bio": "bio", "languages": "languages",
    "dialects": "dialects", "specialties": "specialties", "credentials": "credentials",
    "yearsExperience": "years_experience", "availability": "availability", "photoUrl": "photo_url",
    "rating": "rating", "ratingCount": "rating_count", "onboardingStatus": "onboarding_status",
    "verificationStatus": "verification_status", "credentialStatus": "credential_status",
    "serviceLocation": "service_location", "serviceOptions": "service_options", "verifiedBy": "verified_by",
    "verifiedAt": "verified_at", "createdAt": "created_at", "updatedAt": "updated_at",
}


class MySqlAccountRepository:
    public_fields = {"uid", "displayName", "email", "phone", "role", "status", "createdAt", "updatedAt"}

    def __init__(self, session): self.session = session

    def get(self, uid):
        row = self.session.get(SqlUser, uid)
        return _document(row, ACCOUNT_FIELDS, "uid") if row else None

    def all(self):
        return [{key: value for key, value in _document(row, ACCOUNT_FIELDS, "uid").items() if key in self.public_fields}
                for row in self.session.scalars(select(SqlUser)).all()]

    def find_by_email(self, email):
        value = normalize_email(email)
        if not value: return None
        row = self.session.scalar(select(SqlUser).where(SqlUser.email_normalized == value).limit(1))
        return self._lookup(row, include_phone=False)

    def find_by_phone(self, phone):
        value = normalize_phone(phone)
        if not value: return None
        row = self.session.scalar(select(SqlUser).where(SqlUser.phone_normalized == value).limit(1))
        return self._lookup(row, include_phone=True)

    @staticmethod
    def _lookup(row, include_phone):
        if not row: return None
        data = _document(row, ACCOUNT_FIELDS, "uid")
        keys = {"uid", "displayName", "email", "role", "status"}
        if include_phone: keys.add("phone")
        result = {key: data.get(key) for key in keys}
        result["status"] = data.get("status", "active")
        return result

    def update_status(self, uid, status):
        row = self.session.get(SqlUser, uid)
        if not row: return None
        _touch(row, {"status": status, "updatedAt": _now()}, ACCOUNT_FIELDS)
        _commit(self.session)
        return _document(row, ACCOUNT_FIELDS, "uid")


class MySqlTranslatorRepository:
    public_fields = {"bio", "credentials", "dialects", "displayName", "languages", "photoUrl", "rating",
                     "ratingCount", "serviceLocation", "serviceOptions", "specialties", "verificationStatus",
                     "yearsExperience"}

    def __init__(self, session): self.session = session

    def all_public(self):
        rows = self.session.scalars(select(SqlTranslator).where(SqlTranslator.verification_status == "verified")).all()
        return [self._public(row) for row in rows]

    def get(self, translator_id, public=True):
        row = self.session.get(SqlTranslator, translator_id)
        if not row or (public and row.verification_status != "verified"): return None
        return self._public(row) if public else _document(row, TRANSLATOR_FIELDS)

    def get_private(self, translator_id):
        row = self.session.get(SqlInterpreterPrivate, translator_id)
        if not row: return {"id": translator_id}
        fields = {"uid": "uid", "email": "email", "phone": "phone", "credentialDocuments": "credential_documents",
                  "verificationNotes": "verification_notes", "verifiedBy": "verified_by", "verifiedAt": "verified_at",
                  "createdAt": "created_at", "updatedAt": "updated_at"}
        return _document(row, fields)

    def search(self, language=None, languages=None, dialect=None, specialty=None, available_now=False,
               minimum_rating=0, verified_only=False, service_mode="both", latitude=None, longitude=None,
               radius_miles=None, limit=100):
        requested = {str(value).casefold() for value in (languages or []) if str(value).strip()}
        if language: requested.add(str(language).casefold())
        dialect, specialty = (dialect or "").casefold(), (specialty or "").casefold()
        mode = str(service_mode or "both").casefold()
        if mode not in {"nearby", "remote", "both"}: raise ValueError("Search mode must be nearby, remote, or both.")
        radius = None if radius_miles in (None, "", "anywhere") else float(radius_miles)
        if radius is not None and radius not in {5, 10, 25, 50, 100}:
            raise ValueError("Distance must be 5, 10, 25, 50, 100, or anywhere.")
        has_origin = latitude not in (None, "") and longitude not in (None, "")
        if has_origin: latitude, longitude = validate_coordinates(latitude, longitude)
        elif mode == "nearby" or radius is not None: raise ValueError("A location is required for a nearby search.")
        stmt = select(SqlTranslator).where(SqlTranslator.verification_status == "verified").limit(max(20, min(int(limit), 100)))
        rows = self.session.scalars(stmt).all()
        results = []
        for row in rows:
            data = _document(row, TRANSLATOR_FIELDS)
            if requested and not requested.issubset({str(x).casefold() for x in data.get("languages", [])}): continue
            if dialect and dialect not in {str(x).casefold() for x in data.get("dialects", [])}: continue
            if specialty and specialty not in {str(x).casefold() for x in data.get("specialties", [])}: continue
            if available_now and not (data.get("availability") or {}).get("availableNow"): continue
            if float(data.get("rating") or 0) < float(minimum_rating or 0): continue
            options, location = data.get("serviceOptions") or {}, data.get("serviceLocation") or {}
            distance = None
            if has_origin and location.get("showOnMap") and location.get("latitude") is not None and location.get("longitude") is not None:
                distance = haversine_miles(latitude, longitude, location["latitude"], location["longitude"])
            nearby = bool(options.get("inPerson") and distance is not None and distance <= min(radius or float(options.get("radiusMiles") or 25), float(options.get("radiusMiles") or 25)))
            remote = bool(options.get("remote", True))
            if mode == "nearby" and not nearby: continue
            if mode == "remote" and not remote: continue
            if mode == "both" and has_origin and radius is not None and not (nearby or remote): continue
            profile = self._public(row)
            if distance is not None: profile["distanceMiles"] = round(distance, 1)
            profile["matchType"] = "nearby" if nearby else "remote" if remote else "anywhere"
            results.append(profile)
        results.sort(key=lambda item: (bool((item.get("availability") or {}).get("availableNow")), float(item.get("rating") or 0), int(item.get("ratingCount") or 0)), reverse=True)
        return results[:max(1, min(int(limit), 100))]

    def pending_verification(self):
        rows = self.session.scalars(select(SqlTranslator).where(
            SqlTranslator.credential_status == "submitted",
            or_(SqlTranslator.verification_status != "verified", SqlTranslator.verification_status.is_(None)))).all()
        result = []
        for row in rows:
            data = _document(row, TRANSLATOR_FIELDS)
            private = self.get_private(row.id)
            data["credentialDocuments"] = private.get("credentialDocuments", data.get("credentialDocuments", []))
            result.append(data)
        return result

    def set_verification(self, translator_id, status, reviewer_id, notes=""):
        if status not in {"verified", "rejected", "needs_changes"}: raise ValueError("Invalid verification status.")
        row = self.session.get(SqlTranslator, translator_id)
        if not row: return None
        now = _now()
        _touch(row, {"verificationStatus": status, "credentialStatus": "approved" if status == "verified" else status,
                     "onboardingStatus": status, "verifiedBy": reviewer_id, "verifiedAt": now, "updatedAt": now}, TRANSLATOR_FIELDS)
        private = self.session.get(SqlInterpreterPrivate, translator_id)
        if private:
            fields = {"verificationNotes": "verification_notes", "verifiedBy": "verified_by", "verifiedAt": "verified_at"}
            _touch(private, {"verificationNotes": notes, "verifiedBy": reviewer_id, "verifiedAt": now}, fields)
        _commit(self.session)
        return _document(row, TRANSLATOR_FIELDS)

    def update_availability(self, translator_id, availability):
        row = self.session.get(SqlTranslator, translator_id)
        if not row: return None
        _touch(row, {"availability": dict(availability), "updatedAt": _now()}, TRANSLATOR_FIELDS)
        _commit(self.session)
        return _document(row, TRANSLATOR_FIELDS)

    def _public(self, row):
        data = _document(row, TRANSLATOR_FIELDS)
        profile = {key: data[key] for key in self.public_fields if key in data}
        availability = data.get("availability") or {}
        profile["availability"] = {"availableNow": bool(availability.get("availableNow", False)),
            "days": availability.get("days", []) if isinstance(availability.get("days", []), list) else [],
            "start": availability.get("start", ""), "end": availability.get("end", "")}
        location = data.get("serviceLocation") or {}
        if location.get("showOnMap"):
            profile["serviceLocation"] = {key: location.get(key) for key in ("city", "state", "country", "latitude", "longitude", "geohash", "showOnMap")}
        else: profile.pop("serviceLocation", None)
        options = data.get("serviceOptions") or {}
        profile["serviceOptions"] = {"inPerson": bool(options.get("inPerson", False)), "remote": bool(options.get("remote", True)), "radiusMiles": int(options.get("radiusMiles") or 25)}
        try:
            reviews = self.session.scalars(select(SqlReview).where(SqlReview.interpreter_id == row.id, SqlReview.moderation_status == "visible").order_by(SqlReview.created_at.desc()).limit(5)).all()
            profile["recentReviews"] = [{
                "id": review.id,
                "authorName": review.author_name or "FiniSpeak customer",
                "rating": review.rating,
                "text": review.text or "",
                "createdAt": review.created_at,
            } for review in reviews]
        except Exception:
            # Match the existing discovery behavior: malformed/unavailable
            # review data must not hide an otherwise valid interpreter.
            self.session.rollback()
            profile["recentReviews"] = []
        profile["id"] = row.id
        return profile


class MySqlCallRepository:
    def __init__(self, session): self.session = session

    @staticmethod
    def is_participant(call, uid): return uid in {call.get("callerId"), call.get("receiverId"), call.get("translatorId")}

    def create(self, caller, receiver, translator=None, language=None, dialect=None, specialty=None, purpose="", scheduled_at=None):
        now, call_id = _now(), _new_id()
        data = {"callerId": caller["uid"], "callerName": caller.get("displayName") or caller.get("email") or "FiniSpeak customer",
            "receiverId": receiver["uid"], "receiverName": receiver.get("displayName") or receiver.get("email") or "FiniSpeak customer",
            "translatorId": translator.get("id") if translator else None, "translatorName": translator.get("displayName") if translator else None,
            "status": "ringing", "translationStatus": "requested" if translator or language else "not_requested", "language": language,
            "dialect": dialect, "specialty": specialty, "purpose": purpose, "scheduledAt": scheduled_at,
            "createdAt": now, "updatedAt": now, "startedAt": None, "endedAt": None}
        row = SqlCall(id=call_id, raw_document=data, migrated_at=now, mutation_version=1, **{column: data.get(api) for api, column in CALL_FIELDS.items()})
        self.session.add(row); _commit(self.session)
        return {"id": call_id, **data}

    def get(self, call_id):
        row = self.session.get(SqlCall, call_id)
        return _document(row, CALL_FIELDS) if row else None

    def for_user(self, uid):
        rows = self.session.scalars(select(SqlCall).where(or_(SqlCall.caller_id == uid, SqlCall.receiver_id == uid, SqlCall.translator_id == uid)).order_by(SqlCall.created_at.desc())).all()
        return [_document(row, CALL_FIELDS) for row in rows]

    def transition(self, call_id, next_state):
        row = self.session.scalar(select(SqlCall).where(SqlCall.id == call_id).with_for_update())
        if not row: return None
        if next_state not in CallModel.state_transitions.get(row.status, set()):
            self.session.rollback(); raise ValueError(f"A call cannot move from {row.status or 'unknown'} to {next_state}.")
        now, changes = _now(), {"status": next_state, "updatedAt": _now()}
        if next_state in {"connected", "active"} and not row.started_at: changes["startedAt"] = now
        if next_state in CallModel.terminal_states: changes["endedAt"] = now
        _touch(row, changes, CALL_FIELDS); _commit(self.session)
        return _document(row, CALL_FIELDS)

    def request_translator(self, call_id, language=None, languages=None, language_confidence=None, dialect=None, specialty=None, recommended_ids=None):
        row = self.session.get(SqlCall, call_id)
        if not row: return None
        changes = {"translationStatus": "requested", "updatedAt": _now()}
        if language: changes["detectedLanguage"] = language
        if languages:
            values = languages if isinstance(languages, (list, tuple, set)) else [languages]
            changes["requestedLanguages"] = list(dict.fromkeys(str(value).strip() for value in values if str(value).strip()))
        if language_confidence is not None: changes["detectedLanguageConfidence"] = max(0.0, min(1.0, float(language_confidence)))
        if dialect: changes["dialect"] = dialect
        if specialty: changes["specialty"] = specialty
        if recommended_ids is not None:
            changes["recommendedTranslatorIds"] = recommended_ids
            changes["routingStatus"] = "matched" if recommended_ids else "unmatched"
        _touch(row, changes, CALL_FIELDS); _commit(self.session)
        return _document(row, CALL_FIELDS)

    def claim_translator(self, call_id, translator):
        row = self.session.scalar(select(SqlCall).where(SqlCall.id == call_id).with_for_update())
        if not row: return None
        if row.translation_status not in {"requested", "connected"}:
            self.session.rollback(); raise ValueError("This call is not requesting an interpreter.")
        if row.translator_id and row.translator_id != translator["uid"]:
            self.session.rollback(); raise PermissionError("Another interpreter has already accepted this call.")
        _touch(row, {"translatorId": translator["uid"], "translatorName": translator.get("displayName") or translator.get("email") or "FiniSpeak interpreter", "translationStatus": "connected", "updatedAt": _now()}, CALL_FIELDS)
        _commit(self.session)
        return _document(row, CALL_FIELDS)


PARTICIPANT_FIELDS = {"uid": "uid", "role": "role", "displayName": "display_name", "joinedAt": "joined_at", "leftAt": "left_at", "microphoneEnabled": "microphone_enabled", "cameraEnabled": "camera_enabled"}
TRANSCRIPT_FIELDS = {"speakerId": "speaker_id", "speakerRole": "speaker_role", "speakerName": "speaker_name", "language": "language", "languageConfidence": "language_confidence", "primaryLanguage": "primary_language", "primaryLanguageConfidence": "primary_language_confidence", "languageSampleCount": "language_sample_count", "languageConfirmationRequired": "language_confirmation_required", "text": "text", "isFinal": "is_final", "createdAt": "created_at", "clientCreatedAt": "client_created_at"}
REVIEW_FIELDS = {"authorId": "author_id", "authorName": "author_name", "callId": "call_id", "rating": "rating", "text": "text", "moderationStatus": "moderation_status", "createdAt": "created_at"}


class MySqlParticipantRepository:
    def __init__(self, session): self.session = session
    def for_call(self, call_id):
        return [_document(row, PARTICIPANT_FIELDS) for row in self.session.scalars(select(SqlParticipant).where(SqlParticipant.call_id == call_id)).all()]
    def add(self, call_id, uid, role, display_name):
        now = _now(); row = self.session.get(SqlParticipant, (call_id, uid))
        data = {"uid": uid, "role": role, "displayName": display_name, "joinedAt": now}
        if row: _touch(row, data, PARTICIPANT_FIELDS)
        else:
            row = SqlParticipant(call_id=call_id, id=uid, raw_document=data, migrated_at=now, mutation_version=1,
                                 uid=uid, role=role, display_name=display_name, joined_at=now); self.session.add(row)
        _commit(self.session); return {"id": uid, **data}


class MySqlTranscriptRepository:
    def __init__(self, session): self.session = session
    def for_call(self, call_id, limit=500):
        rows = self.session.scalars(select(SqlTranscript).where(SqlTranscript.call_id == call_id).order_by(SqlTranscript.created_at, SqlTranscript.id).limit(min(max(int(limit), 1), 5000))).all()
        return [_document(row, TRANSCRIPT_FIELDS) for row in rows]
    def add(self, call_id, transcript_id, data):
        now = _now(); values = dict(data); row = self.session.get(SqlTranscript, (call_id, transcript_id))
        if row: _touch(row, values, TRANSCRIPT_FIELDS)
        else:
            row = SqlTranscript(call_id=call_id, id=transcript_id, raw_document=values, migrated_at=now, mutation_version=1,
                **{column: values.get(api) for api, column in TRANSCRIPT_FIELDS.items()}); self.session.add(row)
        _commit(self.session); return {"id": transcript_id, **values}


class MySqlReviewRepository:
    def __init__(self, session): self.session = session
    def for_interpreter(self, interpreter_id, visible_only=True, limit=20):
        stmt = select(SqlReview).where(SqlReview.interpreter_id == interpreter_id)
        if visible_only: stmt = stmt.where(SqlReview.moderation_status == "visible")
        rows = self.session.scalars(stmt.order_by(SqlReview.created_at.desc()).limit(limit)).all()
        return [_document(row, REVIEW_FIELDS) for row in rows]
    def create(self, interpreter_id, author, call_id, rating, text):
        call = self.session.get(SqlCall, call_id)
        if not call or call.status != "ended": raise ValueError("Reviews can only be added after a completed session.")
        if author["uid"] not in {call.caller_id, call.receiver_id}: raise PermissionError("Only a customer from this session may leave a review.")
        if call.translator_id != interpreter_id: raise ValueError("The selected interpreter did not participate in this session.")
        review_id = f"{call_id}-{author['uid']}"
        if self.session.get(SqlReview, (interpreter_id, review_id)): raise ValueError("A review has already been submitted for this session.")
        now = _now(); data = {"authorId": author["uid"], "authorName": author.get("displayName") or "FiniSpeak customer", "callId": call_id, "rating": rating, "text": text, "moderationStatus": "visible", "createdAt": now}
        self.session.add(SqlReview(interpreter_id=interpreter_id, id=review_id, raw_document=data, migrated_at=now, mutation_version=1, **{column: data.get(api) for api, column in REVIEW_FIELDS.items()}))
        try:
            self._recalculate(interpreter_id)
        except Exception:
            self.session.rollback()
            raise
        _commit(self.session)
        return {"id": review_id, **data}
    def moderate(self, interpreter_id, review_id, status):
        if status not in {"visible", "flagged", "hidden"}: raise ValueError("Invalid moderation status.")
        row = self.session.get(SqlReview, (interpreter_id, review_id))
        if not row: return None
        _touch(row, {"moderationStatus": status}, REVIEW_FIELDS)
        try:
            self._recalculate(interpreter_id)
        except Exception:
            self.session.rollback()
            raise
        _commit(self.session)
        return _document(row, REVIEW_FIELDS)
    def _recalculate(self, interpreter_id):
        self.session.flush()
        reviews = self.session.scalars(select(SqlReview).where(SqlReview.interpreter_id == interpreter_id, SqlReview.moderation_status == "visible")).all()
        translator = self.session.get(SqlTranslator, interpreter_id)
        if translator:
            rating = sum(float(row.rating or 0) for row in reviews) / len(reviews) if reviews else None
            _touch(translator, {"rating": rating, "ratingCount": len(reviews), "updatedAt": _now()}, TRANSLATOR_FIELDS)


ORGANIZATION_FIELDS = {"name": "name", "contactEmail": "contact_email", "domain": "domain", "status": "status", "notes": "notes", "createdBy": "created_by", "createdAt": "created_at", "updatedAt": "updated_at"}


class MySqlOrganizationRepository:
    allowed_statuses = {"active", "pending", "suspended"}
    def __init__(self, session): self.session = session
    def all(self):
        rows = [_document(row, ORGANIZATION_FIELDS) for row in self.session.scalars(select(SqlOrganization)).all()]
        return sorted(rows, key=lambda row: str(row.get("name") or row.get("displayName") or "").casefold())
    def create(self, data, actor_id):
        name, email = str(data.get("name") or "").strip(), normalize_email(data.get("contactEmail"))
        if not name: raise ValueError("Organization name is required.")
        if len(name) > 160 or len(email) > 320: raise ValueError("Organization fields are too long.")
        status = str(data.get("status") or "active")
        if status not in self.allowed_statuses: raise ValueError("Invalid organization status.")
        now, record_id = _now(), _new_id(); payload = {"name": name, "contactEmail": email, "domain": str(data.get("domain") or "").strip().lower(), "status": status, "notes": str(data.get("notes") or "").strip()[:2000], "createdBy": actor_id, "createdAt": now, "updatedAt": now}
        self.session.add(SqlOrganization(id=record_id, raw_document=payload, migrated_at=now, mutation_version=1, **{column: payload.get(api) for api, column in ORGANIZATION_FIELDS.items()})); _commit(self.session)
        return {"id": record_id, **payload}
    def update(self, organization_id, data):
        row = self.session.get(SqlOrganization, organization_id)
        if not row: return None
        changes = {key: str(data.get(key) or "").strip() for key in ("name", "contactEmail", "domain", "notes") if key in data}
        for key in ("contactEmail", "domain"):
            if key in changes: changes[key] = changes[key].lower()
        if "status" in data:
            if data["status"] not in self.allowed_statuses: raise ValueError("Invalid organization status.")
            changes["status"] = data["status"]
        changes["updatedAt"] = _now(); _touch(row, changes, ORGANIZATION_FIELDS); _commit(self.session)
        return _document(row, ORGANIZATION_FIELDS)


API_KEY_FIELDS = {"organizationId": "organization_id", "name": "name", "tokenHash": "token_hash", "prefix": "prefix", "scopes": "scopes", "minuteLimit": "minute_limit", "dailyQuota": "daily_quota", "status": "status", "createdBy": "created_by", "revokedBy": "revoked_by", "createdAt": "created_at", "updatedAt": "updated_at", "expiresAt": "expires_at", "lastUsedAt": "last_used_at", "revokedAt": "revoked_at"}


class MySqlApiAccessRepository:
    allowed_scopes = {"interpreters:read", "routing:read", "usage:read"}
    def __init__(self, session, pepper=None): self.session, self.pepper = session, pepper
    def _digest(self, token):
        pepper = self.pepper if self.pepper is not None else os.getenv("FINISPEAK_API_KEY_PEPPER", "").strip()
        if not pepper: raise RuntimeError("FINISPEAK_API_KEY_PEPPER is not configured.")
        return hmac.new(pepper.encode(), token.encode(), hashlib.sha256).hexdigest()
    @staticmethod
    def _public(data): return {key: value for key, value in data.items() if key != "tokenHash"}
    def create(self, data, actor_id):
        organization_id, name, scopes = str(data.get("organizationId") or "").strip(), str(data.get("name") or "").strip(), sorted(set(data.get("scopes") or []))
        if not organization_id or not name: raise ValueError("organizationId and name are required.")
        if not scopes or not set(scopes).issubset(self.allowed_scopes): raise ValueError("At least one valid API scope is required.")
        key_id, now = secrets.token_hex(10), _now(); token = f"fs_live_{key_id}_{secrets.token_urlsafe(32)}"
        payload = {"organizationId": organization_id, "name": name[:160], "tokenHash": self._digest(token), "prefix": f"fs_live_{key_id}", "scopes": scopes, "minuteLimit": min(max(int(data.get("minuteLimit") or 60), 1), 10000), "dailyQuota": min(max(int(data.get("dailyQuota") or 10000), 1), 10000000), "status": "active", "createdBy": actor_id, "createdAt": now, "updatedAt": now, "expiresAt": now + timedelta(days=max(1, min(int(data.get("expiresInDays") or 365), 730))), "lastUsedAt": None}
        self.session.add(SqlApiKey(id=key_id, raw_document=payload, migrated_at=now, mutation_version=1, **{column: payload.get(api) for api, column in API_KEY_FIELDS.items()})); _commit(self.session)
        return {"id": key_id, **self._public(payload), "token": token}
    def all(self):
        rows = [{"id": row.id, **self._public(_document(row, API_KEY_FIELDS))} for row in self.session.scalars(select(SqlApiKey).order_by(SqlApiKey.created_at.desc())).all()]
        return rows
    def revoke(self, key_id, actor_id):
        row = self.session.get(SqlApiKey, key_id)
        if not row: return None
        now = _now(); _touch(row, {"status": "revoked", "revokedBy": actor_id, "revokedAt": now, "updatedAt": now}, API_KEY_FIELDS); _commit(self.session)
        return self._public(_document(row, API_KEY_FIELDS))
    def authenticate(self, token):
        parts = str(token or "").split("_", 3)
        if len(parts) != 4 or parts[:2] != ["fs", "live"] or not parts[2] or not parts[3]: return None
        row = self.session.get(SqlApiKey, parts[2])
        if not row or row.status != "active" or not hmac.compare_digest(str(row.token_hash or ""), self._digest(token)): return None
        expires = row.expires_at
        if expires and (expires.replace(tzinfo=timezone.utc) if expires.tzinfo is None else expires) <= _now(): return None
        return self._public(_document(row, API_KEY_FIELDS))
    def consume_quota(self, api_key, now=None):
        now = now or _now(); specs = (("m", now.strftime("%Y%m%d%H%M"), "minute", int(api_key.get("minuteLimit") or 60), timedelta(days=2)), ("d", now.strftime("%Y%m%d"), "day", int(api_key.get("dailyQuota") or 10000), timedelta(days=35)))
        rows = []
        for marker, bucket, kind, limit, expiry in specs:
            row_id = f"{api_key['id']}_{marker}_{bucket}"
            row = self.session.scalar(select(SqlApiUsageCounter).where(SqlApiUsageCounter.id == row_id).with_for_update())
            count = int(row.count if row else 0)
            if count >= limit:
                self.session.rollback(); return {"allowed": False, "reason": "rate_limit" if kind == "minute" else "daily_quota", "minuteRemaining": 0 if kind == "minute" else max(0, specs[0][3] - int(rows[0].count if rows else 0)), "dailyRemaining": 0 if kind == "day" else max(0, specs[1][3])}
            if not row:
                payload = {"keyId": api_key["id"], "organizationId": api_key.get("organizationId"), "kind": kind, "bucket": bucket, "count": 0, "updatedAt": now, "expiresAt": now + expiry}
                row = SqlApiUsageCounter(id=row_id, key_id=api_key["id"], organization_id=api_key.get("organizationId"), kind=kind, bucket=bucket, count=0, updated_at=now, expires_at=now + expiry, raw_document=payload, migrated_at=now, mutation_version=1); self.session.add(row)
            row.count += 1; rows.append(row)
        key = self.session.get(SqlApiKey, api_key["id"])
        if key: _touch(key, {"lastUsedAt": now}, API_KEY_FIELDS)
        _commit(self.session)
        return {"allowed": True, "minuteRemaining": max(0, specs[0][3] - rows[0].count), "dailyRemaining": max(0, specs[1][3] - rows[1].count)}
    def record_usage(self, api_key, endpoint, method, status_code, duration_ms, request_id):
        now = _now(); payload = {"keyId": api_key["id"], "organizationId": api_key.get("organizationId"), "endpoint": endpoint, "method": method, "statusCode": int(status_code), "durationMs": int(duration_ms), "requestId": request_id, "createdAt": now}
        self.session.add(SqlApiUsageEvent(id=_new_id(), key_id=api_key["id"], organization_id=api_key.get("organizationId"), endpoint=endpoint, method=method, status_code=int(status_code), duration_ms=int(duration_ms), request_id=request_id, created_at=now, raw_document=payload, migrated_at=now, mutation_version=1)); _commit(self.session)
    def usage_summary(self, limit=500):
        rows = self.session.scalars(select(SqlApiUsageEvent).order_by(SqlApiUsageEvent.created_at.desc()).limit(min(max(int(limit), 1), 5000))).all()
        events = [_document(row, {"keyId": "key_id", "organizationId": "organization_id", "endpoint": "endpoint", "method": "method", "statusCode": "status_code", "durationMs": "duration_ms", "requestId": "request_id", "createdAt": "created_at"}) for row in rows]
        errors = [event for event in events if int(event.get("statusCode") or 0) >= 400]
        return {"requests": len(events), "errors": len(errors), "errorRate": round(len(errors) / len(events), 4) if events else 0, "averageDurationMs": round(sum(int(event.get("durationMs") or 0) for event in events) / len(events), 1) if events else 0, "events": events[:100]}


class MySqlTaxonomyRepository:
    collections = {"languages": SqlReferenceLanguage, "dialects": SqlReferenceDialect, "specialties": SqlReferenceSpecialty}
    def __init__(self, session): self.session = session
    def all_active(self):
        result = {}
        for key, model in self.collections.items():
            result[key] = sorted(self.session.scalars(select(model.name).where(model.active.is_(True))).all(), key=str.lower)
        return result


METRIC_FIELDS = {"callId": "call_id", "eventType": "event_type", "detectedLanguage": "detected_language", "confidence": "confidence", "confirmedLanguage": "confirmed_language", "corrected": "corrected", "sampleCount": "sample_count", "createdAt": "created_at"}


class MySqlLanguageMetricsRepository:
    def __init__(self, session): self.session = session
    def record(self, call_id, event_type, detected_language=None, confidence=None, confirmed_language=None, sample_count=None):
        now, record_id = _now(), _new_id(); data = {"callId": call_id, "eventType": event_type, "detectedLanguage": detected_language, "confidence": confidence, "confirmedLanguage": confirmed_language, "corrected": bool(confirmed_language and detected_language and confirmed_language != detected_language), "sampleCount": sample_count, "createdAt": now}
        self.session.add(SqlLanguageDetectionMetric(id=record_id, raw_document=data, migrated_at=now, mutation_version=1, **{column: data.get(api) for api, column in METRIC_FIELDS.items()})); _commit(self.session)
        return {"id": record_id, **data}
    def summary(self, limit=2000):
        rows = self.session.scalars(select(SqlLanguageDetectionMetric).order_by(SqlLanguageDetectionMetric.created_at.desc()).limit(min(max(int(limit), 1), 10000))).all()
        events = [_document(row, METRIC_FIELDS) for row in rows]; samples = [e for e in events if e.get("eventType") == "sample"]; confirmations = [e for e in events if e.get("eventType") == "confirmation"]; corrections = [e for e in confirmations if e.get("corrected")]; low = [e for e in samples if e.get("confidence") is None or float(e.get("confidence") or 0) < .78]; by_language = {}
        for event in samples: by_language[event.get("detectedLanguage") or "unknown"] = by_language.get(event.get("detectedLanguage") or "unknown", 0) + 1
        return {"sampleEvents": len(samples), "confirmationEvents": len(confirmations), "correctionRate": round(len(corrections) / len(confirmations), 4) if confirmations else 0, "lowConfidenceRate": round(len(low) / len(samples), 4) if samples else 0, "byLanguage": by_language, "recentEvents": events[:100]}
