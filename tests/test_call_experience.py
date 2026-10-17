import unittest
from datetime import datetime, timezone

from models.sql_models import SqlCall, SqlTranscript
from repositories.mysql import MySqlCallRepository, MySqlTranscriptRepository
from services.call_access import is_call_participant, participant_ids
from services.call_experience_service import build_experience_changes
from services.summary_service import summarize_lines
from services.translation_service import explain_term, translate_text


class FakeSession:
    def __init__(self, rows=None, scalar=None):
        self.rows = rows or {}
        self.scalar_value = scalar
        self.commits = 0
        self.rollbacks = 0

    def get(self, model, key):
        return self.rows.get((model, key))

    def scalar(self, statement):
        return self.scalar_value

    def add(self, row):
        self.rows[(type(row), (getattr(row, "call_id", None), row.id) if hasattr(row, "call_id") else row.id)] = row

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def call_row():
    now = datetime.now(timezone.utc)
    return SqlCall(
        id="call-1", caller_id="customer-1", receiver_id="customer-2", status="connected",
        raw_document={"callerId": "customer-1", "receiverId": "customer-2", "processingModes": {}},
        migrated_at=now, mutation_version=1, created_at=now,
    )


class CallExperienceTests(unittest.TestCase):
    def test_guest_membership_extends_the_existing_call(self):
        call = {"callerId": "a", "receiverId": "b", "translatorId": None, "guestIds": ["guest-1", ""]}
        self.assertEqual(participant_ids(call), {"a", "b", "guest-1"})
        self.assertTrue(is_call_participant(call, "guest-1"))
        self.assertFalse(is_call_participant(call, "stranger"))

    def test_glossary_translation_and_provider_override(self):
        offline = translate_text("Hello, thank you.", "en", "es")
        self.assertEqual(offline["status"], "translated")
        self.assertIn("hola", offline["text"].casefold())
        self.assertIn("gracias", offline["text"].casefold())
        online = translate_text("Hello", "English", "French", online=True, transport=lambda text, source, target: "Bonjour")
        self.assertEqual(online["text"], "Bonjour")
        self.assertEqual(online["provider"], "provider")
        same = translate_text("Hello", "en", "en")
        self.assertEqual(same["status"], "unchanged")

    def test_terminology_explains_a_selected_word(self):
        explained = explain_term("interpreter", "en", "es")
        self.assertIn("intérprete", explained["translation"])
        self.assertIn("language", explained["definition"].casefold())
        with self.assertRaises(ValueError):
            explain_term("", "en", "es")

    def test_summary_extracts_points_and_action_items(self):
        summary = summarize_lines([
            {"speaker": "Ada", "text": "Please schedule a meeting about the treatment plan."},
            {"speaker": "Ken", "text": "I will send the document after the call."},
            {"speaker": "Ada", "text": "The treatment plan needs a clear follow up."},
        ])
        self.assertGreaterEqual(len(summary["points"]), 1)
        self.assertTrue(any("send the document" in item.lower() for item in summary["actions"]))
        self.assertEqual(summarize_lines([])["text"], "")

    def test_summary_save_requires_consent_and_invite_uses_lookup(self):
        call = {"callerId": "customer-1", "receiverId": "customer-2", "invitations": [], "documents": []}
        actor = {"uid": "customer-1"}
        with self.assertRaisesRegex(ValueError, "consent"):
            build_experience_changes(call, actor, "save-summary", {"lines": [{"speaker": "Ada", "text": "Please schedule a meeting."}]})
        saved = build_experience_changes(call, actor, "save-summary", {"consent": True, "lines": [{"speaker": "Ada", "text": "Please schedule a meeting about treatment."}]})
        self.assertTrue(saved["savedSummaries"][0]["consent"])
        invited = build_experience_changes(call, actor, "invite", {"email": "ken@example.com"}, lambda email: {"uid": "customer-3", "displayName": "Ken"})
        self.assertEqual(invited["invitations"][0]["status"], "pending")
        accepted = build_experience_changes({"invitations": invited["invitations"]}, {"uid": "customer-3"}, "accept-invite", {})
        self.assertIn("customer-3", accepted["guestIds"])
        with self.assertRaises(PermissionError):
            build_experience_changes(call, {"uid": "stranger"}, "set-interpreter", {"avatarId": "nova"})

    def test_repository_patches_experience_without_new_columns(self):
        row = call_row()
        session = FakeSession(scalar=row)
        result = MySqlCallRepository(session).patch_experience("call-1", "customer-1", {"guestIds": ["customer-3"]})
        self.assertEqual(result["guestIds"], ["customer-3"])
        self.assertEqual(session.commits, 1)
        self.assertTrue(MySqlCallRepository.is_participant(result, "customer-3"))

    def test_transcript_translation_is_stored_beside_the_original(self):
        now = datetime.now(timezone.utc)
        transcript = SqlTranscript(
            call_id="call-1", id="line-1", text="Hello", language="en", is_final=True,
            raw_document={"text": "Hello", "language": "en"}, migrated_at=now, mutation_version=1,
        )
        session = FakeSession(rows={(SqlTranscript, ("call-1", "line-1")): transcript})
        saved = MySqlTranscriptRepository(session).annotate_translation("call-1", "line-1", "es", "Hola", "translated")
        self.assertEqual(saved["text"], "Hello")
        self.assertEqual(saved["translations"]["es"]["text"], "Hola")


if __name__ == "__main__":
    unittest.main()
