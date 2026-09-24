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

    credential_path = os.getenv("FIREBASE_CREDENTIALS", "").strip()
    project_id = os.getenv("FIREBASE_PROJECT_ID", "finispeak").strip()

    if not firebase_admin._apps:
        if credential_path:
            # Local development: use the configured service-account JSON.
            cred = credentials.Certificate(credential_path)
            firebase_admin.initialize_app(
                cred,
                options={"projectId": project_id},
            )
        else:
            # Cloud Run / Google Cloud:
            # use Application Default Credentials from the runtime
            # service account instead of requiring a JSON key.
            firebase_admin.initialize_app(
                options={"projectId": project_id}
            )

    _db = firestore.client()
    return _db
