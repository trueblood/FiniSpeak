from flask import jsonify

from repositories.provider import repository_proxy

TaxonomyModel = repository_proxy("taxonomy")


def index():
    try:
        return jsonify(TaxonomyModel.all_active())
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 503
