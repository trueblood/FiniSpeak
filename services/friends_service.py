"""Persistent friend contacts and session-backed online presence."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from extensions import db
from models.sql_models import SqlAuthSession, SqlFriend, SqlUser
from repositories.normalization import canonicalize_phone, normalize_email, normalize_phone


ONLINE_WINDOW = timedelta(minutes=3)


def _now():
    return datetime.now(timezone.utc)


def _online(user_id, now):
    return db.session.scalar(select(SqlAuthSession.id).where(
        SqlAuthSession.user_id == user_id,
        SqlAuthSession.revoked_at.is_(None),
        SqlAuthSession.expires_at > now,
        SqlAuthSession.last_seen_at >= now - ONLINE_WINDOW,
    ).limit(1)) is not None


def _friend_payload(link, user, now):
    return {
        "uid": user.id,
        "displayName": user.display_name or user.email,
        "email": user.email,
        "phone": user.phone,
        "nickname": link.nickname or "",
        "savedPhone": link.saved_phone or user.phone or "",
        "online": _online(user.id, now),
        "lastUpdatedAt": link.updated_at.isoformat() if link.updated_at else None,
    }


def list_friends(owner_id):
    now = _now()
    rows = db.session.execute(
        select(SqlFriend, SqlUser).join(SqlUser, SqlUser.id == SqlFriend.friend_id).where(
            SqlFriend.owner_id == owner_id,
            SqlUser.deleted_at.is_(None),
            SqlUser.status != "deleted",
        ).order_by(SqlUser.display_name, SqlUser.email)
    ).all()
    return [_friend_payload(link, user, now) for link, user in rows]


def add_friend(owner_id, email=None, phone=None, nickname=None, saved_phone=None):
    email_value, phone_value = normalize_email(email), normalize_phone(phone)
    if not email_value and not phone_value:
        raise ValueError("Enter a FiniSpeak email or saved phone number.")
    lookup = SqlUser.email_normalized == email_value if email_value else SqlUser.phone_normalized == phone_value
    user = db.session.scalar(select(SqlUser).where(
        lookup, SqlUser.deleted_at.is_(None), SqlUser.status == "active"
    ).limit(1))
    if not user:
        raise ValueError("That active FiniSpeak account was not found.")
    if user.id == owner_id:
        raise ValueError("You cannot add yourself as a friend.")
    now = _now()
    link = db.session.get(SqlFriend, (owner_id, user.id))
    canonical_saved_phone = canonicalize_phone(saved_phone) if saved_phone else (user.phone or "")
    if saved_phone and not canonical_saved_phone:
        raise ValueError("Enter a valid saved phone number including its country code.")
    if link:
        link.nickname = str(nickname or "").strip()[:160]
        link.saved_phone = canonical_saved_phone
        link.updated_at = now
    else:
        link = SqlFriend(
            owner_id=owner_id, friend_id=user.id,
            nickname=str(nickname or "").strip()[:160],
            saved_phone=canonical_saved_phone,
            created_at=now, updated_at=now,
        )
        db.session.add(link)
    db.session.commit()
    return _friend_payload(link, user, now)


def update_friend(owner_id, friend_id, nickname=None, saved_phone=None):
    link = db.session.get(SqlFriend, (owner_id, friend_id))
    user = db.session.get(SqlUser, friend_id)
    if not link or not user or user.deleted_at or user.status == "deleted":
        return None
    if nickname is not None:
        link.nickname = str(nickname).strip()[:160]
    if saved_phone is not None:
        canonical = canonicalize_phone(saved_phone)
        if saved_phone and not canonical:
            raise ValueError("Enter a valid saved phone number including its country code.")
        link.saved_phone = canonical
    link.updated_at = _now()
    db.session.commit()
    return _friend_payload(link, user, _now())


def remove_friend(owner_id, friend_id):
    link = db.session.get(SqlFriend, (owner_id, friend_id))
    if not link:
        return False
    db.session.delete(link)
    db.session.commit()
    return True
