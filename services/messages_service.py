"""Direct messages and friend groups inside the existing account graph."""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from extensions import db
from models.sql_models import (
    SqlAuthSession, SqlConversation, SqlConversationMember, SqlFriend, SqlMessage, SqlUser,
)
from repositories.normalization import normalize_email, normalize_phone


ONLINE_WINDOW = timedelta(minutes=3)
MAX_BODY = 2000
MAX_TITLE = 80
MAX_GROUP_MEMBERS = 50
PREVIEW_LENGTH = 140
MESSAGE_PAGE = 100


def _now():
    return datetime.now(timezone.utc)


def _aware(value):
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=timezone.utc)


def _iso(value):
    value = _aware(value)
    return value.isoformat() if value else None


def _display_name(user):
    if not user:
        return "Former member"
    return user.display_name or user.email or "FiniSpeak user"


def _online(user_id, now):
    return db.session.scalar(select(SqlAuthSession.id).where(
        SqlAuthSession.user_id == user_id,
        SqlAuthSession.revoked_at.is_(None),
        SqlAuthSession.expires_at > now,
        SqlAuthSession.last_seen_at >= now - ONLINE_WINDOW,
    ).limit(1)) is not None


def _active_user(user_id):
    user = db.session.get(SqlUser, user_id) if user_id else None
    if not user or user.deleted_at or user.status != "active":
        return None
    return user


def _require_active_sender(user_id):
    user = _active_user(user_id)
    if not user:
        raise ValueError("This FiniSpeak account cannot send messages.")
    return user


def _find_user(email=None, phone=None, user_id=None):
    if user_id:
        user = _active_user(str(user_id))
    else:
        email_value, phone_value = normalize_email(email), normalize_phone(phone)
        if not email_value and not phone_value:
            raise ValueError("Enter a FiniSpeak email or choose a friend.")
        lookup = SqlUser.email_normalized == email_value if email_value else SqlUser.phone_normalized == phone_value
        user = db.session.scalar(select(SqlUser).where(
            lookup, SqlUser.deleted_at.is_(None), SqlUser.status == "active"
        ).limit(1))
    if not user:
        raise ValueError("That active FiniSpeak account was not found.")
    return user


def _membership(conversation_id, user_id, active_only=True):
    membership = db.session.get(SqlConversationMember, (conversation_id, user_id))
    if not membership or (active_only and membership.left_at):
        return None
    return membership


def _conversation_or_none(conversation_id, user_id):
    conversation = db.session.get(SqlConversation, conversation_id)
    membership = _membership(conversation_id, user_id) if conversation else None
    if not conversation or not membership:
        return None, None
    return conversation, membership


def _members(conversation_id, now):
    rows = db.session.execute(
        select(SqlConversationMember, SqlUser).join(
            SqlUser, SqlUser.id == SqlConversationMember.user_id
        ).where(
            SqlConversationMember.conversation_id == conversation_id,
            SqlConversationMember.left_at.is_(None),
        ).order_by(SqlConversationMember.joined_at, SqlUser.display_name)
    ).all()
    members = [{
        "uid": user.id,
        "displayName": _display_name(user),
        "role": membership.role,
        "online": _online(user.id, now),
    } for membership, user in rows]
    members.sort(key=lambda item: (item["role"] != "owner", item["displayName"].lower()))
    return members


def _latest_message(conversation_id):
    return db.session.scalar(
        select(SqlMessage).where(SqlMessage.conversation_id == conversation_id).order_by(
            SqlMessage.created_at.desc(), SqlMessage.id.desc()
        ).limit(1)
    )


def _preview(message, viewer_id):
    if not message:
        return None
    sender = db.session.get(SqlUser, message.sender_id) if message.sender_id else None
    body = message.body if len(message.body) <= PREVIEW_LENGTH else f"{message.body[:PREVIEW_LENGTH - 1]}…"
    return {
        "body": body,
        "senderName": _display_name(sender),
        "createdAt": _iso(message.created_at),
        "mine": message.sender_id == viewer_id,
    }


def _unread(conversation_id, user_id, last_read_at):
    statement = select(func.count()).select_from(SqlMessage).where(
        SqlMessage.conversation_id == conversation_id,
        SqlMessage.sender_id != user_id,
    )
    if last_read_at:
        statement = statement.where(SqlMessage.created_at > last_read_at)
    return int(db.session.scalar(statement) or 0)


def _title(conversation, members, viewer_id):
    if conversation.kind == "group":
        return conversation.title or "Group"
    others = [member for member in members if member["uid"] != viewer_id]
    if others:
        return others[0]["displayName"]
    return "Direct message"


def _payload(conversation, viewer_id, now, membership):
    members = _members(conversation.id, now)
    return {
        "id": conversation.id,
        "kind": conversation.kind,
        "title": _title(conversation, members, viewer_id),
        "viewerRole": membership.role,
        "memberCount": len(members),
        "members": members,
        "unreadCount": _unread(conversation.id, viewer_id, membership.last_read_at),
        "lastMessage": _preview(_latest_message(conversation.id), viewer_id),
        "updatedAt": _iso(conversation.updated_at),
    }


def _message_payload(message, viewer_id):
    sender = db.session.get(SqlUser, message.sender_id) if message.sender_id else None
    return {
        "id": message.id,
        "senderId": message.sender_id,
        "senderName": _display_name(sender),
        "body": message.body,
        "createdAt": _iso(message.created_at),
        "mine": message.sender_id == viewer_id,
    }


def _clean_body(body):
    text = str(body or "").replace("\x00", "").strip()
    if not text:
        raise ValueError("Write a message before sending.")
    if len(text) > MAX_BODY:
        raise ValueError(f"Messages can be up to {MAX_BODY} characters.")
    return text


def list_conversations(user_id):
    now = _now()
    rows = db.session.execute(
        select(SqlConversation, SqlConversationMember).join(
            SqlConversationMember, SqlConversationMember.conversation_id == SqlConversation.id
        ).where(
            SqlConversationMember.user_id == user_id,
            SqlConversationMember.left_at.is_(None),
        ).order_by(SqlConversation.updated_at.desc(), SqlConversation.id.desc())
    ).all()
    return [_payload(conversation, user_id, now, membership) for conversation, membership in rows]


def _add_member(conversation_id, user, role, now):
    membership = db.session.get(SqlConversationMember, (conversation_id, user.id))
    if membership and not membership.left_at:
        raise ValueError("They are already in this group.")
    if membership:
        membership.role = role
        membership.left_at = None
        membership.joined_at = now
        membership.last_read_at = now
        return membership
    membership = SqlConversationMember(
        conversation_id=conversation_id, user_id=user.id, role=role,
        joined_at=now, last_read_at=now,
    )
    db.session.add(membership)
    return membership


def _direct_key(first_id, second_id):
    return ":".join(sorted((first_id, second_id)))


def open_direct(user_id, email=None, phone=None, other_user_id=None):
    _require_active_sender(user_id)
    other = _find_user(email, phone, other_user_id)
    if other.id == user_id:
        raise ValueError("You cannot message yourself.")
    key = _direct_key(user_id, other.id)
    existing = db.session.scalar(select(SqlConversation).where(SqlConversation.direct_key == key).limit(1))
    now = _now()
    created = existing is None
    if existing:
        conversation = existing
        for person, role in ((user_id, "owner"), (other.id, "member")):
            membership = db.session.get(SqlConversationMember, (conversation.id, person))
            if membership and membership.left_at:
                membership.left_at = None
                membership.joined_at = now
                membership.last_read_at = now
            elif not membership:
                user = _active_user(person)
                if user:
                    _add_member(conversation.id, user, role, now)
    else:
        conversation = SqlConversation(
            id=str(uuid.uuid4()), kind="direct", direct_key=key, created_by=user_id,
            created_at=now, updated_at=now,
        )
        db.session.add(conversation)
        db.session.flush()
        _add_member(conversation.id, _active_user(user_id), "owner", now)
        _add_member(conversation.id, other, "member", now)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        conversation = db.session.scalar(select(SqlConversation).where(SqlConversation.direct_key == key).limit(1))
        created = False
        if not conversation:
            raise
    membership = _membership(conversation.id, user_id)
    return _payload(conversation, user_id, _now(), membership), created


def _friend_ids(owner_id):
    return set(db.session.scalars(select(SqlFriend.friend_id).where(SqlFriend.owner_id == owner_id)).all())


def create_group(user_id, title, member_ids):
    owner = _require_active_sender(user_id)
    name = str(title or "").replace("\x00", "").strip()
    if not name or len(name) > MAX_TITLE:
        raise ValueError(f"Enter a group name up to {MAX_TITLE} characters.")
    if not isinstance(member_ids, list):
        raise ValueError("Choose at least one friend.")
    chosen = []
    seen = set()
    for member_id in member_ids:
        if not isinstance(member_id, str) or not member_id or member_id == user_id or member_id in seen:
            continue
        seen.add(member_id)
        chosen.append(member_id)
    if not chosen:
        raise ValueError("Choose at least one friend.")
    if len(chosen) + 1 > MAX_GROUP_MEMBERS:
        raise ValueError(f"Groups can include up to {MAX_GROUP_MEMBERS} people.")
    friends = _friend_ids(user_id)
    people = []
    for member_id in chosen:
        if member_id not in friends:
            raise ValueError("Add them as a friend before adding them to a group.")
        person = _active_user(member_id)
        if not person:
            raise ValueError("That active FiniSpeak account was not found.")
        people.append(person)
    now = _now()
    conversation = SqlConversation(
        id=str(uuid.uuid4()), kind="group", title=name, created_by=user_id,
        created_at=now, updated_at=now,
    )
    db.session.add(conversation)
    db.session.flush()
    _add_member(conversation.id, owner, "owner", now)
    for person in people:
        _add_member(conversation.id, person, "member", now)
    db.session.commit()
    membership = _membership(conversation.id, user_id)
    return _payload(conversation, user_id, _now(), membership)


def get_conversation(user_id, conversation_id):
    conversation, membership = _conversation_or_none(conversation_id, user_id)
    if not conversation:
        return None
    now = _now()
    membership.last_read_at = now
    db.session.commit()
    messages = db.session.execute(
        select(SqlMessage).where(SqlMessage.conversation_id == conversation.id).order_by(
            SqlMessage.created_at.desc(), SqlMessage.id.desc()
        ).limit(MESSAGE_PAGE + 1)
    ).scalars().all()
    truncated = len(messages) > MESSAGE_PAGE
    visible = list(reversed(messages[:MESSAGE_PAGE]))
    return {
        "conversation": _payload(conversation, user_id, _now(), membership),
        "messages": [_message_payload(message, user_id) for message in visible],
        "truncated": truncated,
    }


def post_message(user_id, conversation_id, body):
    _require_active_sender(user_id)
    conversation, membership = _conversation_or_none(conversation_id, user_id)
    if not conversation:
        return None
    text = _clean_body(body)
    now = _now()
    message = SqlMessage(
        id=str(uuid.uuid4()), conversation_id=conversation.id, sender_id=user_id,
        body=text, created_at=now,
    )
    conversation.updated_at = now
    membership.last_read_at = now
    db.session.add(message)
    db.session.commit()
    return _message_payload(message, user_id)


def add_member(user_id, conversation_id, member_id):
    _require_active_sender(user_id)
    conversation, membership = _conversation_or_none(conversation_id, user_id)
    if not conversation:
        return None
    if conversation.kind != "group":
        raise ValueError("Only group chats can add people.")
    if membership.role != "owner":
        raise ValueError("Only the group owner can add people.")
    if not isinstance(member_id, str) or not member_id:
        raise ValueError("Choose a friend to add.")
    if member_id == user_id:
        raise ValueError("You are already in this group.")
    if member_id not in _friend_ids(user_id):
        raise ValueError("Add them as a friend before adding them to a group.")
    person = _active_user(member_id)
    if not person:
        raise ValueError("That active FiniSpeak account was not found.")
    active_count = db.session.scalar(select(func.count()).select_from(SqlConversationMember).where(
        SqlConversationMember.conversation_id == conversation.id,
        SqlConversationMember.left_at.is_(None),
    )) or 0
    already = _membership(conversation.id, person.id)
    if not already and active_count >= MAX_GROUP_MEMBERS:
        raise ValueError(f"Groups can include up to {MAX_GROUP_MEMBERS} people.")
    now = _now()
    _add_member(conversation.id, person, "member", now)
    conversation.updated_at = now
    db.session.commit()
    return _payload(conversation, user_id, _now(), membership)


def remove_member(user_id, conversation_id, member_id):
    conversation, membership = _conversation_or_none(conversation_id, user_id)
    if not conversation:
        return None
    if conversation.kind != "group":
        raise ValueError("Only group chats can remove people.")
    target_id = user_id if member_id in {None, "", "me"} else str(member_id)
    leaving = target_id == user_id
    if not leaving and membership.role != "owner":
        raise ValueError("Only the group owner can remove people.")
    target = _membership(conversation.id, target_id)
    if not target:
        raise ValueError("That person is not in this group.")
    now = _now()
    if target.role == "owner":
        successor = db.session.scalar(
            select(SqlConversationMember).where(
                SqlConversationMember.conversation_id == conversation.id,
                SqlConversationMember.user_id != target.user_id,
                SqlConversationMember.left_at.is_(None),
            ).order_by(SqlConversationMember.joined_at, SqlConversationMember.user_id).limit(1)
        )
        if successor:
            successor.role = "owner"
            target.role = "member"
    target.left_at = now
    conversation.updated_at = now
    db.session.commit()
    if leaving:
        return {"left": True}
    refreshed = _membership(conversation.id, user_id)
    return {"conversation": _payload(conversation, user_id, _now(), refreshed)}
