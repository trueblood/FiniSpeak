from flask import jsonify

from models.taxonomy import TaxonomyModel


def index():
    try:
        return jsonify(TaxonomyModel.all_active())
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 503
