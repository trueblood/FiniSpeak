import io
import os
import unittest
import zipfile
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from models.sql_models import SqlCall, SqlTranscript
from repositories.mysql import MySqlCallRepository, MySqlTranscriptRepository
from services.call_access import is_call_participant, participant_ids
from services.document_extract import extract_document_text
from services.call_experience_service import build_experience_changes
from services.summary_service import summarize_lines
from services.transcript_policy import (
    attach_speech_translation,
    build_speech_transcript,
    consent_changes,
    partition_transcripts,
    policy_public,
)
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
        self.assertEqual(online["message"], "Translation updated.")
        same = translate_text("Hello", "en", "en")
        self.assertEqual(same["status"], "unchanged")
        self.assertIn("different translation language", same["message"])
        sentence = translate_text(
            "The patient needs an appointment tomorrow morning.",
            "en",
            "es",
            online=True,
            transport=lambda text, source, target: "El paciente necesita una cita mañana por la mañana.",
        )
        self.assertEqual(sentence["text"], "El paciente necesita una cita mañana por la mañana.")
        self.assertEqual(sentence["provider"], "provider")

        def provider_down(text, source, target):
            raise RuntimeError("provider down")

        glossary = translate_text("Thank you", "en", "es", online=True, transport=provider_down)
        self.assertEqual(glossary["status"], "translated")
        self.assertEqual(glossary["provider"], "glossary")
        self.assertIn("gracias", glossary["text"].casefold())
        self.assertIn("Glossary", glossary["message"])
        missed = translate_text(
            "The patient needs an appointment tomorrow morning.",
            "en",
            "es",
            online=True,
            transport=provider_down,
        )
        self.assertEqual(missed["status"], "unavailable")
        self.assertIn("patient", missed["text"].casefold())
        self.assertIn("no glossary match", missed["message"].casefold())

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
        rated = build_experience_changes(call, actor, "rate-call", {"callQuality": 4, "audioLogging": "5"})
        self.assertEqual(rated["callQualityRating"], 4)
        self.assertEqual(rated["audioLoggingRating"], 5)
        self.assertEqual(rated["callRatingAuthorId"], "customer-1")
        with self.assertRaisesRegex(ValueError, "1 to 5"):
            build_experience_changes(call, actor, "rate-call", {"callQuality": 6})
        notes = build_experience_changes(call, actor, "save-notes", {"text": "  Follow up on the meeting.\nBring the document.  "})
        self.assertEqual(notes["callNotes"], "Follow up on the meeting.\nBring the document.")
        self.assertEqual(notes["callNotesAuthorId"], "customer-1")
        cleared = build_experience_changes(call, actor, "save-notes", {"text": ""})
        self.assertEqual(cleared["callNotes"], "")
        with self.assertRaises(PermissionError):
            build_experience_changes(call, {"uid": "stranger"}, "save-notes", {"text": "no"})
        with self.assertRaises(ValueError):
            build_experience_changes(call, actor, "save-notes", {"text": "x" * 4001})

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

    def test_flagged_moment_is_a_timestamped_follow_up(self):
        call = {"callerId": "customer-1", "receiverId": "customer-2"}
        actor = {"uid": "customer-1", "displayName": "Ada"}
        flagged = build_experience_changes(call, actor, "flag-moment", {
            "id": "moment-1", "elapsedLabel": "01:12", "transcriptId": "line-1",
            "speakerName": "Ken", "text": "Please send the document.",
        })
        moment = flagged["keyMoments"][0]
        self.assertEqual(moment["id"], "moment-1")
        self.assertTrue(moment["followUp"])
        self.assertTrue(moment["createdAt"])
        self.assertEqual(moment["elapsedLabel"], "01:12")
        self.assertEqual(moment["authorName"], "Ada")
        again = build_experience_changes({**call, **flagged}, actor, "flag-moment", {"id": "moment-1", "text": "duplicate"})
        self.assertEqual(len(again["keyMoments"]), 1)
        resolved = build_experience_changes({**call, **flagged}, actor, "resolve-moment", {"id": "moment-1"})
        self.assertFalse(resolved["keyMoments"][0]["followUp"])
        self.assertTrue(resolved["keyMoments"][0]["resolvedAt"])
        with self.assertRaises(PermissionError):
            build_experience_changes(call, {"uid": "stranger"}, "flag-moment", {"text": "no"})

    def test_transcript_consent_retention_and_speech_line(self):
        call = {"callerId": "customer-1"}
        granted = consent_changes("customer-1", True)
        self.assertTrue(granted["transcriptConsent"]["granted"])
        self.assertEqual(granted["transcriptConsent"]["retentionDays"], 90)
        self.assertFalse(policy_public(call)["consentGranted"])
        self.assertFalse(policy_public(granted)["storesAudio"])
        self.assertIn("90 days", policy_public(granted)["statement"])
        revoked = consent_changes("customer-1", False)
        self.assertFalse(revoked["transcriptConsent"]["granted"])
        saved = build_experience_changes(call, {"uid": "customer-1"}, "set-transcript-consent", {"granted": True})
        self.assertTrue(saved["transcriptConsent"]["granted"])

        source = {
            "id": "line-1", "speakerId": "customer-1", "speakerRole": "caller", "speakerName": "Ada",
            "language": "en", "text": "Hello, thank you.", "isFinal": True,
            "createdAt": datetime.now(timezone.utc), "clientCreatedAt": 1_700_000_000_000,
        }
        speech = build_speech_transcript(source, "es", "Spanish", online=False)
        self.assertEqual(speech["kind"], "speech")
        self.assertEqual(speech["sourceTranscriptId"], "line-1")
        self.assertEqual(speech["language"], "es")
        self.assertEqual(speech["speakerId"], "customer-1")
        self.assertIn("hola", speech["text"].casefold())
        self.assertIn("gracias", speech["text"].casefold())
        self.assertEqual(speech["clientCreatedAt"], 1_700_000_000_001)
        paired = attach_speech_translation(source, speech)
        self.assertEqual(paired["translations"]["es"]["kind"], "speech")
        unchanged = build_speech_transcript({**source, "text": "zzzz-not-a-phrase"}, "en", "en", online=False)
        self.assertIsNone(unchanged)
        same_language = build_speech_transcript({**source, "language": "en", "text": "Hello"}, "en", None, online=False)
        self.assertEqual(same_language["language"], "es")

        now = datetime.now(timezone.utc)
        fresh, expired = partition_transcripts([
            {"id": "new", "createdAt": now.isoformat()},
            {"id": "old", "createdAt": (now - timedelta(days=91)).isoformat()},
        ], now=now, retention_days_value=90)
        self.assertEqual([row["id"] for row in fresh], ["new"])
        self.assertEqual([row["id"] for row in expired], ["old"])


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


class TranscriptStorageTests(unittest.TestCase):
    def setUp(self):
        from app import create_app
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    def test_published_rate_is_optional_and_bounded(self):
        from controllers.translators_controller import published_rate
        self.assertIsNone(published_rate(""))
        self.assertIsNone(published_rate(None))
        self.assertEqual(published_rate("12.5"), 12.5)
        with self.assertRaisesRegex(ValueError, "price per minute"):
            published_rate("nope")
        with self.assertRaisesRegex(ValueError, "between 0 and 10000"):
            published_rate(-1)

    @patch.dict(os.environ, {"FINISPEAK_SPEECH_TRANSLATION": "glossary"})
    @patch("controllers.calls_controller.TranscriptModel")
    @patch("controllers.calls_controller.CallModel")
    @patch("controllers.calls_controller.identity_or_response")
    def test_saved_transcript_requires_consent_and_keeps_a_speech_line(self, identity, calls, transcripts):
        identity.return_value = ({"uid": "customer-1", "role": "customer", "displayName": "Ada"}, None)
        calls.is_participant.return_value = True
        calls.get.return_value = {"callerId": "customer-1", "language": "Spanish"}
        transcripts.add.side_effect = lambda call_id, transcript_id, data: {"id": transcript_id, **data}

        denied = self.client.post("/api/calls/call-1/transcripts", json={
            "id": "line-1", "text": "Hello", "language": "en", "captionLanguage": "es",
        })
        self.assertEqual(denied.status_code, 403)
        self.assertIn("consent", denied.get_json()["error"].lower())
        transcripts.add.assert_not_called()

        calls.get.return_value = {
            "callerId": "customer-1", "language": "Spanish",
            "transcriptConsent": {"granted": True, "retentionDays": 90},
        }
        saved = self.client.post("/api/calls/call-1/transcripts", json={
            "id": "line-1", "text": "Hello", "language": "en", "captionLanguage": "es",
        })
        self.assertEqual(saved.status_code, 201)
        body = saved.get_json()
        self.assertEqual(body["transcript"]["speakerName"], "Ada")
        self.assertEqual(body["transcript"]["translations"]["es"]["kind"], "speech")
        self.assertEqual(body["speechTranscript"]["kind"], "speech")
        self.assertEqual(body["speechTranscript"]["language"], "es")
        self.assertIn("hola", body["speechTranscript"]["text"].casefold())
        self.assertFalse(body["policy"]["storesAudio"])

        transcripts.delete_for_call.return_value = 2
        deleted = self.client.delete("/api/calls/call-1/transcripts")
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(deleted.get_json()["deleted"], 2)

        now = datetime.now(timezone.utc)
        transcripts.for_call.return_value = [
            {"id": "fresh", "createdAt": now.isoformat(), "text": "Hello"},
            {"id": "expired", "createdAt": (now - timedelta(days=91)).isoformat(), "text": "Old"},
        ]
        listed = self.client.get("/api/calls/call-1/transcripts")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual([row["id"] for row in listed.get_json()["transcripts"]], ["fresh"])
        transcripts.delete_ids.assert_called_once()
        self.assertIn("expired", transcripts.delete_ids.call_args.args[1])


if __name__ == "__main__":
    unittest.main()
