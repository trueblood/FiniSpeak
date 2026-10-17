"""Shared call membership checks.

Guest accounts are stored on the call document so an invitation can join the
existing WebRTC session without a schema change.
"""


def participant_ids(call):
    if not call:
        return set()
    ids = {call.get("callerId"), call.get("receiverId"), call.get("translatorId")}
    guests = call.get("guestIds") or []
    if isinstance(guests, list):
        ids.update(str(value) for value in guests if value)
    ids.discard(None)
    ids.discard("")
    return ids


def is_call_participant(call, uid):
    return bool(uid) and uid in participant_ids(call)


def pending_invitee_ids(call):
    invites = call.get("invitations") if call else None
    if not isinstance(invites, list):
        return set()
    return {
        str(item.get("inviteeId"))
        for item in invites
        if isinstance(item, dict) and item.get("status") == "pending" and item.get("inviteeId")
    }
