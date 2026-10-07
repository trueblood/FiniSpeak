from flask import jsonify

from controllers.controller_utils import identity_or_response, json_body
from models.organization import OrganizationModel


def index():
    _, error = identity_or_response(admin=True)
    if error:
        return error
    return jsonify({"organizations": OrganizationModel.all()})


def create():
    identity, error = identity_or_response(admin=True)
    if error:
        return error
    try:
        return jsonify({"organization": OrganizationModel.create(json_body(), identity["uid"])}), 201
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


def update(organization_id):
    _, error = identity_or_response(admin=True)
    if error:
        return error
    try:
        organization = OrganizationModel.update(organization_id, json_body())
        return (jsonify({"organization": organization}), 200) if organization else (jsonify({"error": "Organization not found."}), 404)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
