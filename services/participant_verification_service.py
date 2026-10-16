from flask import request

from repositories.provider import get_repository
from services.auth_service import authenticate_request


def verify_participant(_token, call_id):
    identity = authenticate_request(request)
    call = get_repository("calls").get(call_id)
    if not call:
        raise RuntimeError("Call not found.")
    if identity["uid"] not in [call.get("callerId"), call.get("receiverId"), call.get("translatorId")]:
        raise RuntimeError("You are not a participant in this call.")
    return identity
