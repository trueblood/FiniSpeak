from flask import jsonify

from controllers.controller_utils import identity_or_response, json_body
from models.translator import TranslatorModel


def update():
    identity, error = identity_or_response()
    if error:
        return error
    if identity.get("role") not in {"translator", "admin"}:
        return jsonify({"error": "An interpreter account is required."}), 403
    data = json_body()
    availability = {
        "availableNow": bool(data.get("availableNow")),
        "days": data.get("days") if isinstance(data.get("days"), list) else [],
        "start": str(data.get("start") or ""),
        "end": str(data.get("end") or ""),
        "timezone": str(data.get("timezone") or "UTC"),
    }
    profile = TranslatorModel.update_availability(identity["uid"], availability)
    return (jsonify({"profile": profile}), 200) if profile else (jsonify({"error": "Interpreter profile not found"}), 404)
