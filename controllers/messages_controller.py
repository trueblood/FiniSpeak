from flask import jsonify, request

from controllers.controller_utils import identity_or_response, json_body
from services.messages_service import (
    add_member, create_group, get_conversation, list_conversations, open_direct, post_message, remove_member,
)


def _missing():
    return jsonify({"error": "Conversation not found."}), 404


def conversations():
    identity, error = identity_or_response()
    if error:
        return error
    if request.method == "GET":
        return jsonify({"conversations": list_conversations(identity["uid"])})
    data = json_body()
    kind = data.get("kind")
    try:
        if kind == "group":
            conversation = create_group(identity["uid"], data.get("title"), data.get("memberIds"))
            return jsonify({"conversation": conversation}), 201
        if kind == "direct":
            conversation, created = open_direct(
                identity["uid"], data.get("email"), data.get("phone"), data.get("userId"),
            )
            return jsonify({"conversation": conversation}), 201 if created else 200
        return jsonify({"error": "Choose a direct message or a group."}), 400
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


def conversation_detail(conversation_id):
    identity, error = identity_or_response()
    if error:
        return error
    detail = get_conversation(identity["uid"], conversation_id)
    return jsonify(detail) if detail else _missing()


def messages(conversation_id):
    identity, error = identity_or_response()
    if error:
        return error
    try:
        message = post_message(identity["uid"], conversation_id, json_body().get("body"))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return (jsonify({"message": message}), 201) if message else _missing()


def members(conversation_id):
    identity, error = identity_or_response()
    if error:
        return error
    try:
        conversation = add_member(identity["uid"], conversation_id, json_body().get("userId"))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return (jsonify({"conversation": conversation}), 200) if conversation else _missing()


def member_detail(conversation_id, user_id):
    identity, error = identity_or_response()
    if error:
        return error
    try:
        result = remove_member(identity["uid"], conversation_id, user_id)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(result) if result else _missing()
