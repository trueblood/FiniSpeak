import os

import firebase_admin
from dotenv import load_dotenv
from firebase_admin import credentials, firestore

load_dotenv()

_db = None


def get_db():
    """Return the Firestore client, initializing Firebase on first use."""
    global _db

    if _db is not None:
        return _db

    credential_path = os.getenv("FIREBASE_CREDENTIALS")
    if not credential_path:
        raise RuntimeError(
            "FIREBASE_CREDENTIALS is not configured. Copy .env.example to .env "
            "and point it at your Firebase service-account JSON file."
        )

    if not firebase_admin._apps:
        cred = credentials.Certificate(credential_path)
        firebase_admin.initialize_app(cred)

    _db = firestore.client()
    return _db
