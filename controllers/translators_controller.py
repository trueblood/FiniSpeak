from flask import jsonify

from models.translator import TranslatorModel


def index():
    try:
        return jsonify(TranslatorModel.all_public())
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 503
