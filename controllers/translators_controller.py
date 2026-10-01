from flask import jsonify

from models.translator import TranslatorModel


def index():
    try:
        return jsonify(TranslatorModel.all_public())
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 503


def detail(translator_id):
    try:
        profile = TranslatorModel.get(translator_id)
        return (jsonify(profile), 200) if profile else (jsonify({"error": "Interpreter not found"}), 404)
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 503
