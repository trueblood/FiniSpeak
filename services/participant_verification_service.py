from flask import request

from repositories.provider import get_repository
from services.auth_service import authenticate_request
from services.call_access import is_call_participant


def verify_participant(_token, call_id):
    identity = authenticate_request(request)
    call = get_repository("calls").get(call_id)
    if not call:
        raise RuntimeError("Call not found.")
    if not is_call_participant(call, identity["uid"]):
        raise RuntimeError("You are not a participant in this call.")
    return identity
