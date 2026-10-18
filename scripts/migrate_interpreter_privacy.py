"""Move legacy private interpreter fields into /interpreterPrivate.

Run once with Application Default Credentials or FIREBASE_CREDENTIALS:
    python scripts/migrate_interpreter_privacy.py --dry-run
    python scripts/migrate_interpreter_privacy.py --apply
"""

import argparse
import sys
from pathlib import Path

# Running a file from scripts/ puts that directory—not the repository root—on
# Python's import path. Add the root explicitly so the documented command works
# without requiring callers to set PYTHONPATH.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from google.cloud import firestore

from services.firebase_service import get_db


PRIVATE_FIELDS = ("email", "phone", "credentialDocuments", "verificationNotes")


def migrate(apply_changes=False):
    db = get_db()
    migrated = 0
    for snapshot in db.collection("translators").stream():
        data = snapshot.to_dict()
        private = {field: data[field] for field in PRIVATE_FIELDS if field in data}
        if not private:
            continue
        migrated += 1
        print(f"{snapshot.id}: {', '.join(sorted(private))}")
        if not apply_changes:
            continue
        private["uid"] = snapshot.id
        batch = db.batch()
        batch.set(db.collection("interpreterPrivate").document(snapshot.id), private, merge=True)
        batch.update(snapshot.reference, {field: firestore.DELETE_FIELD for field in private if field in PRIVATE_FIELDS})
        batch.commit()
    print(f"{'Migrated' if apply_changes else 'Would migrate'} {migrated} interpreter profile(s).")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Write the migration. Without this flag the script is read-only.")
    parser.add_argument("--dry-run", action="store_true", help="Explicitly request a read-only preview.")
    args = parser.parse_args()
    if args.apply and args.dry_run:
        parser.error("Choose either --apply or --dry-run.")
    migrate(apply_changes=args.apply)
