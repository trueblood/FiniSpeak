import io
import unittest
import zipfile
from datetime import datetime, timezone

from models.sql_models import SqlCall, SqlTranscript
from repositories.mysql import MySqlCallRepository, MySqlTranscriptRepository
from services.call_access import is_call_participant, participant_ids
from services.document_extract import extract_document_text
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
        punctuated = explain_term("meeting,", "en", "es")
        self.assertEqual(punctuated["term"], "meeting")
        self.assertIn("reunión", punctuated["translation"])
        preferred = explain_term(
            "meeting", "en", "es", online=True,
            transport=lambda text, source, target: "Miembros del Equipo",
        )
        self.assertIn("reunión", preferred["translation"])
        custom = explain_term("hospital", "en", "es", online=True, transport=lambda text, source, target: "hospital")
        self.assertEqual(custom["translation"], "hospital")
        phrase = explain_term(("hello " * 16).strip(), "en", "es")
        self.assertIn("hola", phrase["translation"].casefold())
        with self.assertRaises(ValueError):
            explain_term("", "en", "es")
        with self.assertRaises(ValueError):
            explain_term("...", "en", "es")

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
        phoned = build_experience_changes(call, actor, "invite", {"contact": "+1 (555) 010-1234"}, lambda phone: {"uid": "customer-4", "displayName": "Ada", "phone": phone} if phone == "15550101234" else None)
        self.assertEqual(phoned["invitations"][0]["inviteePhone"], "15550101234")
        with self.assertRaisesRegex(ValueError, "phone number"):
            build_experience_changes(call, actor, "invite", {"contact": "nope"}, lambda _value: None)
        accepted = build_experience_changes({"invitations": invited["invitations"]}, {"uid": "customer-3"}, "accept-invite", {})
        self.assertIn("customer-3", accepted["guestIds"])
        with self.assertRaises(PermissionError):
            build_experience_changes(call, {"uid": "stranger"}, "set-interpreter", {"avatarId": "nova"})
        built = build_experience_changes(call, actor, "set-media", {"mediaMode": "avatar", "avatarId": "custom"})
        self.assertEqual(built, {})
        with self.assertRaisesRegex(ValueError, "Avatar Studio"):
            build_experience_changes(call, actor, "set-media", {"mediaMode": "avatar", "avatarId": "made-up"})
        with self.assertRaisesRegex(ValueError, "Avatar Studio"):
            build_experience_changes(call, actor, "set-interpreter", {"interpreter": {"avatarId": "custom", "active": True}})

    def test_repository_patches_experience_without_new_columns(self):
        row = call_row()
        session = FakeSession(scalar=row)
        result = MySqlCallRepository(session).patch_experience("call-1", "customer-1", {"guestIds": ["customer-3"]})
        self.assertEqual(result["guestIds"], ["customer-3"])
        self.assertEqual(session.commits, 1)
        self.assertTrue(MySqlCallRepository.is_participant(result, "customer-3"))

    def test_document_upload_reads_word_and_pdf_text(self):
        document = io.BytesIO()
        with zipfile.ZipFile(document, "w") as archive:
            archive.writestr(
                "word/document.xml",
                """<?xml version="1.0" encoding="UTF-8"?>
                <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
                <w:body><w:p><w:r><w:t>Schedule the meeting.</w:t></w:r></w:p></w:body></w:document>""",
            )
        text, title = extract_document_text("agenda.docx", document.getvalue())
        self.assertEqual(title, "agenda")
        self.assertIn("Schedule the meeting.", text)
        pdf_text, _pdf_title = extract_document_text("notes.pdf", _minimal_pdf("Hello PDF"))
        self.assertIn("Hello PDF", pdf_text)
        with self.assertRaisesRegex(ValueError, "PDF, Word"):
            extract_document_text("photo.png", b"not a document")

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


def _minimal_pdf(message):
    content = f"BT /F1 24 Tf 72 100 Td ({message}) Tj ET".encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 144] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, body in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{index} 0 obj\n".encode("ascii"))
        output.extend(body)
        output.extend(b"\nendobj\n")
    xref = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.extend(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode("ascii"))
    return bytes(output)


if __name__ == "__main__":
    unittest.main()
