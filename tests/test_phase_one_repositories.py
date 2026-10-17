import hashlib
import hmac
import unittest
from datetime import datetime, timedelta, timezone

from models.sql_models import SqlApiKey, SqlCall, SqlUser
from repositories.config import REPOSITORY_DOMAINS, repository_backends
from repositories.mysql import (
    MySqlAccountRepository, MySqlApiAccessRepository, MySqlCallRepository,
    MySqlLanguageMetricsRepository, MySqlOrganizationRepository,
    MySqlParticipantRepository, MySqlReviewRepository,
    MySqlTaxonomyRepository, MySqlTranscriptRepository,
    MySqlTranslatorRepository,
)


class ScalarRows:
    def __init__(self, rows): self.rows = rows
    def all(self): return list(self.rows)


class FakeSession:
    def __init__(self, rows=None, scalar=None, scalar_rows=None, commit_error=None):
        self.rows, self.scalar_value = rows or {}, scalar
        self.scalar_rows, self.commit_error = list(scalar_rows or []), commit_error
        self.added, self.commits, self.rollbacks, self.flushes = [], 0, 0, 0
    def get(self, model, key): return self.rows.get((model, key))
    def scalar(self, statement): return self.scalar_value
    def scalars(self, statement): return ScalarRows(self.scalar_rows)
    def add(self, row): self.added.append(row)
    def flush(self): self.flushes += 1
    def commit(self):
        if self.commit_error: raise self.commit_error
        self.commits += 1
    def rollback(self): self.rollbacks += 1


def sql_user(uid="user-1", **values):
    now = datetime.now(timezone.utc)
    return SqlUser(id=uid, uid=uid, display_name=values.get("display_name", "Ada"),
        email=values.get("email", "ada@example.com"), email_normalized=values.get("email_normalized", "ada@example.com"),
        phone=values.get("phone", "+1 317 555 0100"), phone_normalized=values.get("phone_normalized", "13175550100"),
        role=values.get("role", "customer"), status=values.get("status", "active"),
        raw_document=values.get("raw_document", {"legacyField": True}), migrated_at=now,
        mutation_version=values.get("mutation_version", 1))


def sql_call(call_id="call-1", **values):
    now = datetime.now(timezone.utc)
    return SqlCall(id=call_id, caller_id=values.get("caller_id", "customer-1"),
        receiver_id=values.get("receiver_id", "customer-2"), translator_id=values.get("translator_id", "translator-1"),
        status=values.get("status", "ended"), translation_status=values.get("translation_status", "connected"),
        raw_document=values.get("raw_document", {}), migrated_at=now,
        mutation_version=values.get("mutation_version", 1), created_at=now)


class PhaseOneContractTests(unittest.TestCase):
    def test_all_domains_default_to_mysql(self):
        self.assertEqual(repository_backends({}), {domain: "mysql" for domain in REPOSITORY_DOMAINS})

    def test_mysql_implementations_cover_every_repository_domain(self):
        implementations = {
            "accounts": MySqlAccountRepository, "translators": MySqlTranslatorRepository,
            "calls": MySqlCallRepository, "participants": MySqlParticipantRepository,
            "transcripts": MySqlTranscriptRepository, "reviews": MySqlReviewRepository,
            "organizations": MySqlOrganizationRepository, "api_access": MySqlApiAccessRepository,
            "taxonomy": MySqlTaxonomyRepository, "language_metrics": MySqlLanguageMetricsRepository,
        }
        self.assertEqual(set(implementations), set(REPOSITORY_DOMAINS))
        self.assertTrue(all(callable(value) for value in implementations.values()))

    def test_construction_does_not_open_a_connection(self):
        session = object()
        repositories = [MySqlAccountRepository(session), MySqlTranslatorRepository(session), MySqlCallRepository(session),
            MySqlParticipantRepository(session), MySqlTranscriptRepository(session), MySqlReviewRepository(session),
            MySqlOrganizationRepository(session), MySqlApiAccessRepository(session, pepper="test"),
            MySqlTaxonomyRepository(session), MySqlLanguageMetricsRepository(session)]
        self.assertTrue(all(repository.session is session for repository in repositories))


class MySqlAccountRepositoryTests(unittest.TestCase):
    def test_get_preserves_firestore_shape_and_unknown_fields(self):
        row = sql_user(raw_document={"displayName": "Old", "custom": "preserved"})
        result = MySqlAccountRepository(FakeSession({(SqlUser, "user-1"): row})).get("user-1")
        self.assertEqual(result, {"uid": "user-1", "displayName": "Ada", "email": "ada@example.com",
            "phone": "+1 317 555 0100", "phoneNormalized": "13175550100",
            "role": "customer", "status": "active", "custom": "preserved"})

    def test_missing_records_match_firestore_none_behavior(self):
        repository = MySqlAccountRepository(FakeSession())
        self.assertIsNone(repository.get("missing"))
        self.assertIsNone(repository.update_status("missing", "active"))
        self.assertIsNone(repository.find_by_email(""))
        self.assertIsNone(repository.find_by_phone("not a phone"))

    def test_duplicate_phone_lookup_fails_closed(self):
        rows = [sql_user("user-1"), sql_user("user-2")]
        repository = MySqlAccountRepository(FakeSession(scalar_rows=rows))
        self.assertIsNone(repository.find_by_phone("+1 317 555 0100"))

    def test_failed_commit_rolls_back(self):
        row = sql_user()
        session = FakeSession({(SqlUser, "user-1"): row}, commit_error=RuntimeError("database unavailable"))
        with self.assertRaisesRegex(RuntimeError, "database unavailable"):
            MySqlAccountRepository(session).update_status("user-1", "suspended")
        self.assertEqual(session.rollbacks, 1)
        self.assertEqual(row.mutation_version, 2)


class MySqlAuthorizationTests(unittest.TestCase):
    def test_duplicate_call_request_returns_existing_record(self):
        caller = {"uid": "customer-1", "displayName": "Caller"}
        key = "same-request"
        call_id = "req_" + hashlib.sha256(f"customer-1:{key}".encode()).hexdigest()[:48]
        existing = sql_call(call_id, status="ringing")
        session = FakeSession({(SqlCall, call_id): existing})
        result = MySqlCallRepository(session).create(caller, {"uid": "customer-2"}, idempotency_key=key)
        self.assertEqual(result["id"], call_id)
        self.assertEqual(session.commits, 0)

    def test_review_rejects_nonparticipant(self):
        session = FakeSession({(SqlCall, "call-1"): sql_call()})
        with self.assertRaisesRegex(PermissionError, "Only a customer"):
            MySqlReviewRepository(session).create("translator-1", {"uid": "intruder"}, "call-1", 5, "text")
        self.assertEqual(session.added, [])

    def test_transcript_converts_browser_epoch_milliseconds_to_datetime(self):
        session = FakeSession()
        result = MySqlTranscriptRepository(session).add("call-1", "line-1", {
            "text": "Recognized speech",
            "clientCreatedAt": 1_792_189_158_329,
        })
        row = session.added[0]
        self.assertIsInstance(row.client_created_at, datetime)
        self.assertEqual(row.client_created_at.tzinfo, timezone.utc)
        self.assertEqual(result["text"], "Recognized speech")
        self.assertEqual(session.commits, 1)

    def test_review_rejects_missing_call(self):
        with self.assertRaisesRegex(ValueError, "completed session"):
            MySqlReviewRepository(FakeSession()).create("translator-1", {"uid": "customer-1"}, "missing", 5, "text")

    def test_call_claim_prevents_overwriting_interpreter(self):
        row = sql_call(translation_status="requested", translator_id="translator-1")
        session = FakeSession(scalar=row)
        with self.assertRaisesRegex(PermissionError, "Another interpreter"):
            MySqlCallRepository(session).claim_translator("call-1", {"uid": "translator-2"})
        self.assertEqual(session.rollbacks, 1)

    def test_request_translator_stores_the_chosen_interpreter(self):
        row = sql_call(status="connected", translation_status="not_requested", translator_id=None, raw_document={})
        session = FakeSession(scalar=row)
        result = MySqlCallRepository(session).request_translator(
            "call-1", languages=["English"], translator_id="translator-9", translator_name="Marcus Johnson")
        self.assertEqual(result["invitedTranslatorId"], "translator-9")
        self.assertEqual(result["invitedTranslatorName"], "Marcus Johnson")
        self.assertEqual(result["translationStatus"], "requested")
        self.assertEqual(result["requestedLanguages"], ["English"])
        self.assertEqual(session.commits, 1)

    def test_language_wide_request_keeps_a_direct_invite(self):
        row = sql_call(status="connected", translation_status="requested", translator_id=None, raw_document={
            "invitedTranslatorId": "translator-9", "invitedTranslatorName": "Marcus Johnson"})
        result = MySqlCallRepository(FakeSession(scalar=row)).request_translator(
            "call-1", language="English", recommended_ids=["translator-9", "translator-2"])
        self.assertEqual(result["invitedTranslatorId"], "translator-9")
        self.assertEqual(result["recommendedTranslatorIds"], ["translator-9", "translator-2"])

    def test_declining_a_direct_invite_hides_it_from_that_interpreter(self):
        row = sql_call(status="connected", translation_status="requested", translator_id=None, raw_document={
            "invitedTranslatorId": "translator-9", "invitedTranslatorName": "Marcus Johnson"})
        result = MySqlCallRepository(FakeSession(scalar=row)).request_translator(
            "call-1", decline_translator_id="translator-9")
        self.assertIsNone(result["invitedTranslatorId"])
        self.assertIn("translator-9", result["declinedTranslatorIds"])
        self.assertEqual(result["translationStatus"], "not_requested")

    def test_claim_rejects_an_interpreter_who_was_not_invited(self):
        row = sql_call(status="connected", translation_status="requested", translator_id=None,
            raw_document={"invitedTranslatorId": "translator-9"})
        session = FakeSession(scalar=row)
        with self.assertRaisesRegex(PermissionError, "sent to another interpreter"):
            MySqlCallRepository(session).claim_translator("call-1", {"uid": "translator-2"})
        self.assertEqual(session.rollbacks, 1)

    def test_claim_lets_the_invited_interpreter_join(self):
        row = sql_call(status="connected", translation_status="requested", translator_id=None,
            raw_document={"invitedTranslatorId": "translator-9", "invitedTranslatorName": "Marcus Johnson"})
        result = MySqlCallRepository(FakeSession(scalar=row)).claim_translator(
            "call-1", {"uid": "translator-9", "displayName": "Marcus Johnson"})
        self.assertEqual(result["translatorId"], "translator-9")
        self.assertEqual(result["translatorName"], "Marcus Johnson")
        self.assertEqual(result["translationStatus"], "connected")
        self.assertIsNone(result["invitedTranslatorId"])

    def test_missing_call_updates_return_none(self):
        repository = MySqlCallRepository(FakeSession())
        self.assertIsNone(repository.transition("missing", "ended"))
        self.assertIsNone(repository.request_translator("missing"))
        self.assertIsNone(repository.set_processing_mode("missing", "customer-1", "streaming"))

    def test_processing_mode_is_scoped_without_changing_another_participant(self):
        row = sql_call(raw_document={"processingModes": {"customer-2": "concurrent"}})
        session = FakeSession(scalar=row)
        result = MySqlCallRepository(session).set_processing_mode("call-1", "customer-1", "streaming")
        self.assertEqual(result["processingModes"], {
            "customer-1": "streaming",
            "customer-2": "concurrent",
        })
        self.assertEqual(session.commits, 1)

    def test_processing_mode_rejects_nonparticipant(self):
        session = FakeSession(scalar=sql_call())
        with self.assertRaisesRegex(PermissionError, "not a participant"):
            MySqlCallRepository(session).set_processing_mode("call-1", "intruder", "streaming")
        self.assertEqual(session.rollbacks, 1)

    def test_missing_records_are_consistent_across_domains(self):
        session = FakeSession()
        self.assertIsNone(MySqlTranslatorRepository(session).get("missing"))
        self.assertEqual(MySqlTranslatorRepository(session).get_private("missing"), {"id": "missing"})
        self.assertIsNone(MySqlOrganizationRepository(session).update("missing", {"status": "active"}))
        self.assertIsNone(MySqlReviewRepository(session).moderate("missing", "review", "hidden"))
        self.assertIsNone(MySqlApiAccessRepository(session, pepper="test").revoke("missing", "admin"))

    def test_empty_child_and_metrics_queries_preserve_response_shapes(self):
        session = FakeSession()
        self.assertEqual(MySqlParticipantRepository(session).for_call("missing"), [])
        self.assertEqual(MySqlTranscriptRepository(session).for_call("missing"), [])
        self.assertEqual(MySqlLanguageMetricsRepository(session).summary(), {
            "sampleEvents": 0, "confirmationEvents": 0, "correctionRate": 0,
            "lowConfidenceRate": 0, "byLanguage": {}, "recentEvents": [],
        })


class MySqlApiAccessRepositoryTests(unittest.TestCase):
    def test_authentication_rejects_malformed_missing_revoked_and_expired(self):
        token, now = "fs_live_key1_secret", datetime.now(timezone.utc)
        self.assertIsNone(MySqlApiAccessRepository(FakeSession(), pepper="pepper").authenticate("bad"))
        self.assertIsNone(MySqlApiAccessRepository(FakeSession(), pepper="pepper").authenticate(token))
        digest = hmac.new(b"pepper", token.encode(), hashlib.sha256).hexdigest()
        revoked = SqlApiKey(id="key1", token_hash=digest, status="revoked", raw_document={}, migrated_at=now, mutation_version=1)
        self.assertIsNone(MySqlApiAccessRepository(FakeSession({(SqlApiKey, "key1"): revoked}), pepper="pepper").authenticate(token))
        expired = SqlApiKey(id="key1", token_hash=digest, status="active", expires_at=now - timedelta(seconds=1), raw_document={}, migrated_at=now, mutation_version=1)
        self.assertIsNone(MySqlApiAccessRepository(FakeSession({(SqlApiKey, "key1"): expired}), pepper="pepper").authenticate(token))

    def test_authentication_never_exposes_hash(self):
        token, now = "fs_live_key1_secret", datetime.now(timezone.utc)
        digest = hmac.new(b"pepper", token.encode(), hashlib.sha256).hexdigest()
        row = SqlApiKey(id="key1", token_hash=digest, status="active", scopes=["usage:read"],
            expires_at=now + timedelta(days=1), raw_document={"tokenHash": digest}, migrated_at=now, mutation_version=1)
        result = MySqlApiAccessRepository(FakeSession({(SqlApiKey, "key1"): row}), pepper="pepper").authenticate(token)
        self.assertEqual(result["id"], "key1")
        self.assertNotIn("tokenHash", result)


if __name__ == "__main__": unittest.main()
