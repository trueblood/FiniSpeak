from flask import jsonify

from controllers.controller_utils import identity_or_response, json_body
from repositories.provider import repository_proxy

TaxonomyModel = repository_proxy("taxonomy")


def index():
    try:
        return jsonify(TaxonomyModel.all_active())
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 503


def create(kind):
    identity, error = identity_or_response(admin=True)
    if error:
        return error
    data = json_body()
    try:
        record = TaxonomyModel.create(kind, data.get("id"), data.get("name"), data.get("extra"))
        return jsonify({"record": record}), 201
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
