import unittest
from pathlib import Path
from unittest.mock import patch

from app import create_app


class MvcRouteTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    def test_home_and_api_catalog(self):
        self.assertEqual(self.client.get("/").status_code, 200)
        static_response = self.client.get("/static/css/style.css")
        self.assertEqual(static_response.status_code, 200)
        static_response.close()
        response = self.client.get("/api")
        self.assertEqual(response.status_code, 200)
        paths = {route["path"] for route in response.get_json()["routes"]}
        self.assertTrue({
            "/api",
            "/api/routes",
            "/api/health",
            "/api/auth/login",
            "/api/files",
            "/api/users/",
            "/api/translators/",
            "/api/calls/",
            "/api/taxonomy",
            "/ws/transcription",
            "/ws/signaling",
            "/ws/camera",
        }.issubset(paths))

    def test_interpreter_onboarding_exposes_explicit_review_workflow(self):
        response = self.client.get("/")
        html = response.get_data(as_text=True)
        self.assertIn('id="submitInterpreterVerification"', html)
        self.assertIn('data-wizard-step="0"', html)
        self.assertIn('data-wizard-step="3"', html)
        self.assertIn('data-wizard-step="4"', html)
        self.assertIn('id="interpreterServiceArea"', html)
        self.assertIn('class="wizard-step-icon"', html)
        self.assertIn('id="interpreterWizardNext"', html)
        self.assertIn('id="interpreterWizardBack"', html)
        self.assertNotIn('<select id="interpreterCredentialStatus">', html)

    def test_interpreter_taxonomy_multiselects_survive_partial_mysql_profiles(self):
        html = self.client.get("/").get_data(as_text=True)
        script = (Path(__file__).parents[1] / "views/static/js/app.js").read_text()

        for field_id in ("interpreterLanguages", "interpreterDialects", "interpreterSpecialties"):
            self.assertIn(f'id="{field_id}"', html)
        for tags_id in ("interpreterLanguagesTags", "interpreterDialectsTags", "interpreterSpecialtiesTags"):
            self.assertIn(f'id="{tags_id}"', html)
        self.assertIn('const languages = Array.isArray(data?.languages) ? data.languages : [];', script)
        self.assertIn('const availabilityDays = Array.isArray(availability.days) ? availability.days : [];', script)
        self.assertIn('const serviceOptions = data?.serviceOptions', script)

        translator_block = script[script.index("if (isTranslator) {"):script.index("try { startDashboardListeners()")]
        self.assertGreater(translator_block.index("await loadTaxonomy();"), translator_block.index('console.error("Interpreter profile load failed:", error);'))

    def test_credential_document_renderer_does_not_shadow_browser_document(self):
        script = (Path(__file__).parents[1] / "views/static/js/app.js").read_text()
        renderer = script[script.index("function renderCredentialDocuments"):
            script.index("function renderCredentialReviewStatus")]

        self.assertIn("visibleDocuments.map(credentialDocument =>", renderer)
        self.assertIn('const row = document.createElement("span");', renderer)
        self.assertNotIn("visibleDocuments.map(document =>", renderer)

    def test_dashboard_exposes_mobile_app_navigation_and_actions(self):
        response = self.client.get("/")
        html = response.get_data(as_text=True)
        self.assertIn('class="mobile-app-header"', html)
        self.assertIn('id="appActionTitle">What do you need today?', html)
        self.assertIn('id="openStartCall"', html)
        self.assertIn('id="openDirectCall"', html)
        self.assertIn(">Call Another User<", html)
        self.assertIn('data-discovery-category="Business"', html)
        self.assertIn('data-dashboard-panel="directory"', html)
        self.assertIn('data-dashboard-panel="classroom" aria-label="Language Classroom"', html)
        self.assertIn('id="dashboardClassroom"', html)
        self.assertIn("billing is not active", html)
        self.assertIn('id="aiLanguageTeacherTitle">AI Language Teacher', html)
        self.assertIn("separate from group classrooms", html)
        self.assertIn("only with the student's permission", html)

    def test_interpreter_profile_offers_direct_chat_and_customer_call_flows(self):
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn('id="profileChatTranslator"', html)
        self.assertIn("Chat with translator", html)
        self.assertIn('id="profileStartCall"', html)
        self.assertIn("Start a call with another person", html)
        script = (Path(__file__).parents[1] / "views/static/js/app.js").read_text()
        self.assertIn('purpose: "translator_chat"', script)
        self.assertIn('$("profileChatTranslator").onclick = startDirectTranslatorChat', script)
        self.assertIn("Translators cannot call other translators.", script)
        self.assertIn("isInterpreterRole(currentProfile?.role)", script)
        self.assertIn("Review recent conversations", script)
        self.assertIn("setCustomerCallActionsVisible(!isTranslator)", script)
        self.assertIn("Host a Language Session", script)
        self.assertIn('id="openLanguageLessonLabel">Book a Language Lesson', html)
        self.assertIn('id="openFindTranslator"', html)
        self.assertIn("setTranslatorDiscoveryVisible(!isTranslator)", script)

    def test_phone_call_prototype_exposes_signup_profile_and_call_fields(self):
        response = self.client.get("/")
        html = response.get_data(as_text=True)
        self.assertIn('id="signupPhone" type="tel"', html)
        self.assertIn('id="profilePhone" type="tel"', html)
        self.assertIn('id="receiverPhone" type="tel"', html)
        self.assertIn('id="friendPhone" type="tel"', html)
        self.assertIn('id="interpreterPhone" type="tel"', html)
        self.assertEqual(html.count('data-phone-country'), 5)
        self.assertIn('id="incomingCallModal"', html)
        self.assertIn('id="acceptIncomingCall"', html)

    def test_phone_forms_submit_country_code_with_national_number(self):
        script = (Path(__file__).parents[1] / "views/static/js/app.js").read_text()
        for phone_id in ("signupPhone", "profilePhone", "interpreterPhone", "receiverPhone", "friendPhone"):
            self.assertIn(f'completePhoneNumber("{phone_id}")', script)
        self.assertIn('countryCode !== "+39"', script)
        self.assertIn('return `${countryCode}${nationalDigits}`', script)
        self.assertIn("countryFlag(iso)", script)
        self.assertIn('option.textContent = `${countryFlag(iso)} ${iso} ${code}`', script)

    @patch("controllers.accounts_controller.AccountModel.update_profile")
    @patch("controllers.accounts_controller.identity_or_response")
    def test_profile_saves_sanitized_public_map_location(self, identity, update_profile):
        identity.return_value = ({"uid": "translator-1", "role": "translator"}, None)
        update_profile.return_value = {"uid": "translator-1", "displayName": "Interpreter"}
        response = self.client.patch("/api/accounts/me", json={
            "displayName": "Interpreter",
            "phone": "+13175550123",
            "profileLocation": {
                "label": "Indianapolis, Indiana, United States",
                "city": "Indianapolis",
                "state": "Indiana",
                "country": "United States",
                "latitude": 39.7684,
                "longitude": -86.1581,
                "showOnMap": True,
            },
        })
        self.assertEqual(response.status_code, 200)
        saved = update_profile.call_args.args[1]["profileLocation"]
        self.assertEqual(saved["latitude"], 39.768)
        self.assertEqual(saved["longitude"], -86.158)
        self.assertTrue(saved["showOnMap"])
        self.assertEqual(saved["geohash"], "dp4dprted")

    def test_call_media_fails_safely_before_creating_a_call_on_http(self):
        script = (Path(__file__).parents[1] / "views/static/js/app.js").read_text()
        create_call = script[script.index("async function createCall"):
            script.index("async function joinCall")]
        self.assertIn("MEDIA_CAPTURE_REQUIRES_SECURE_CONTEXT", script)
        self.assertIn("open http://localhost:8080", script)
        self.assertLess(
            create_call.index("requireMediaCapture();"),
            create_call.index('apiFetch("/api/calls/"'),
        )

    def test_call_validation_stays_in_controller(self):
        self.assertEqual(self.client.post("/api/calls/", json={}).status_code, 400)
        response = self.client.post(
            "/api/calls/",
            json={"callerId": "same", "receiverId": "same"},
        )
        self.assertEqual(response.status_code, 400)

    @patch("controllers.calls_controller.identity_or_response")
    @patch("controllers.calls_controller.CallModel.create", return_value="call-123")
    @patch("controllers.calls_controller.AccountModel.get")
    def test_call_controller_uses_model(self, get_account, create_call, identity):
        identity.return_value = ({"uid": "customer-a", "role": "customer"}, None)
        get_account.return_value = {"uid": "customer-b", "role": "customer", "status": "active", "displayName": "Customer B"}
        create_call.return_value = {"id": "call-123", "status": "ringing"}
        response = self.client.post(
            "/api/calls/",
            json={"receiverId": "customer-b"},
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["callId"], "call-123")
        create_call.assert_called_once()

    @patch("controllers.calls_controller.identity_or_response")
    @patch("controllers.calls_controller.CallModel.create")
    @patch("controllers.calls_controller.AccountModel.get")
    @patch("controllers.calls_controller.TranslatorModel.get")
    def test_direct_translator_chat_resolves_verified_profile_account(self, get_translator, get_account, create_call, identity):
        identity.return_value = ({"uid": "customer-a", "role": "customer"}, None)
        get_translator.side_effect = [
            {"id": "profile-9", "displayName": "Interpreter Nine"},
            {"id": "profile-9", "uid": "translator-9", "displayName": "Interpreter Nine"},
        ]
        get_account.return_value = {
            "uid": "translator-9", "role": "translator", "status": "active", "displayName": "Interpreter Nine"
        }
        create_call.return_value = {"id": "call-direct", "status": "ringing", "purpose": "translator_chat"}

        response = self.client.post(
            "/api/calls/",
            json={"receiverId": "profile-9", "purpose": "translator_chat"},
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["callId"], "call-direct")
        get_account.assert_called_once_with("translator-9")
        args, kwargs = create_call.call_args
        self.assertEqual(args[1]["uid"], "translator-9")
        self.assertEqual(kwargs["purpose"], "translator_chat")
        self.assertIsNone(kwargs["translator"])

    @patch("controllers.calls_controller.CallModel.create", return_value={"id": "call-customer", "status": "ringing"})
    @patch("controllers.calls_controller.AccountModel.get")
    @patch("controllers.calls_controller.TranslatorModel.get")
    @patch("controllers.calls_controller.identity_or_response")
    def test_translator_cannot_call_another_translator(self, identity, get_translator, get_account, create_call):
        identity.return_value = ({"uid": "translator-1", "role": "translator"}, None)
        direct = self.client.post("/api/calls/", json={
            "receiverId": "translator-9", "purpose": "translator_chat",
        })
        self.assertEqual(direct.status_code, 403)
        self.assertEqual(direct.get_json()["error"], "Translators cannot call other translators.")
        get_translator.assert_not_called()

        get_account.return_value = {"uid": "translator-9", "role": "translator", "status": "active"}
        addressed = self.client.post("/api/calls/", json={"receiverId": "translator-9"})
        self.assertEqual(addressed.status_code, 403)
        self.assertEqual(addressed.get_json()["error"], "Translators cannot call other translators.")

        get_account.return_value = {"uid": "customer-2", "role": "customer", "status": "active"}
        invited = self.client.post("/api/calls/", json={
            "receiverId": "customer-2", "translatorId": "translator-9",
        })
        self.assertEqual(invited.status_code, 403)
        self.assertEqual(invited.get_json()["error"], "Translators cannot call other translators.")
        create_call.assert_not_called()

        customer_call = self.client.post("/api/calls/", json={"receiverId": "customer-2"})
        self.assertEqual(customer_call.status_code, 201)

    @patch("controllers.calls_controller.CallModel.request_translator")
    @patch("controllers.calls_controller.CallModel.get")
    @patch("controllers.calls_controller.identity_or_response")
    def test_translator_cannot_invite_another_translator(self, identity, get_call, request_translator):
        identity.return_value = ({"uid": "translator-1", "role": "translator"}, None)
        get_call.return_value = {
            "id": "call-1", "callerId": "customer-1", "receiverId": "translator-1",
            "status": "connected", "translationStatus": "not_requested",
        }
        response = self.client.post("/api/calls/call-1/translator-request", json={"translatorId": "translator-9"})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json()["error"], "Translators cannot call other translators.")
        request_translator.assert_not_called()

    @patch("controllers.translators_controller.TranslatorModel.all_public")
    def test_translator_controller_uses_model(self, all_public):
        all_public.return_value = [{"id": "interpreter-1"}]
        response = self.client.get("/api/translators/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), [{"id": "interpreter-1"}])

    @patch("controllers.taxonomy_controller.TaxonomyModel.all_active")
    def test_taxonomy_controller_uses_model(self, all_active):
        all_active.return_value = {
            "languages": ["English"],
            "dialects": [],
            "specialties": [],
        }
        response = self.client.get("/api/taxonomy")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["languages"], ["English"])

    def test_match_cards_post_the_chosen_translator_and_reuse_incoming_call(self):
        script = (Path(__file__).parents[1] / "views/static/js/app.js").read_text()
        match_list = script[script.index("function renderInterpreterMatches"):script.index("function normalizeLanguageConfidence")]
        request_card = script[script.index("function requestMatchCard"):script.index("function visibleRequestMatches")]
        self.assertIn('card.className = "interpreter-match"', match_list)
        self.assertIn('card.type = "button"', match_list)
        self.assertIn('card.className = "request-match-card"', request_card)
        self.assertIn('card.type = "button"', request_card)
        self.assertIn("bindTranslatorInvite(card, profile)", match_list)
        self.assertIn("bindTranslatorInvite(card, profile)", request_card)
        self.assertIn("translatorId: profile.id", script)
        self.assertIn("/translator-request", script)
        self.assertIn('directInvite ? "Accept" : "Join Call"', script)
        self.assertIn("is calling you", script)
        self.assertIn("decline: true", script)
        self.assertIn('id="incomingCallModal"', (Path(__file__).parents[1] / "views/templates/index.html").read_text())

    @patch("controllers.calls_controller.TranslatorModel.get")
    @patch("controllers.calls_controller.CallModel.request_translator")
    @patch("controllers.calls_controller.CallModel.get")
    @patch("controllers.calls_controller.identity_or_response")
    def test_translator_request_stores_the_chosen_profile(self, identity, get_call, request_translator, get_translator):
        identity.return_value = ({"uid": "customer-1", "role": "customer"}, None)
        get_call.return_value = {
            "id": "call-1", "callerId": "customer-1", "receiverId": "customer-2",
            "status": "connected", "translationStatus": "not_requested", "translatorId": None,
        }
        get_translator.return_value = {"id": "translator-9", "displayName": "Marcus Johnson"}
        request_translator.return_value = {
            "id": "call-1", "translationStatus": "requested",
            "invitedTranslatorId": "translator-9", "invitedTranslatorName": "Marcus Johnson",
            "callerName": "Ada",
        }
        response = self.client.post("/api/calls/call-1/translator-request", json={
            "translatorId": "translator-9", "languages": ["English"],
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["call"]["invitedTranslatorId"], "translator-9")
        request_translator.assert_called_once_with(
            "call-1",
            language=None,
            languages=["English"],
            dialect=None,
            specialty=None,
            translator_id="translator-9",
            translator_name="Marcus Johnson",
        )

    @patch("controllers.calls_controller.CallModel.request_translator")
    @patch("controllers.calls_controller.CallModel.get")
    @patch("controllers.calls_controller.identity_or_response")
    def test_translator_request_requires_a_specific_interpreter(self, identity, get_call, request_translator):
        identity.return_value = ({"uid": "customer-1", "role": "customer"}, None)
        get_call.return_value = {
            "id": "call-1", "callerId": "customer-1", "receiverId": "customer-2",
            "status": "connected", "translationStatus": "not_requested", "translatorId": None,
        }
        response = self.client.post("/api/calls/call-1/translator-request", json={"languages": ["Spanish"]})
        self.assertEqual(response.status_code, 400)
        request_translator.assert_not_called()

    @patch("controllers.calls_controller.CallModel.release_member")
    @patch("controllers.calls_controller.CallModel.transition")
    @patch("controllers.calls_controller.ParticipantModel.mark_left")
    @patch("controllers.calls_controller.ParticipantModel.for_call")
    @patch("controllers.calls_controller.CallModel.is_participant", return_value=True)
    @patch("controllers.calls_controller.CallModel.get")
    @patch("controllers.calls_controller.identity_or_response")
    def test_receiver_end_call_only_disconnects_that_receiver(self, identity, get_call, _participant, for_call, mark_left, transition, release_member):
        identity.return_value = ({"uid": "customer-2", "role": "customer"}, None)
        get_call.return_value = {
            "id": "call-1", "callerId": "customer-1", "receiverId": "customer-2",
            "translatorId": "translator-9", "status": "connected",
        }
        for_call.return_value = [
            {"uid": "customer-1", "leftAt": None},
            {"uid": "customer-2", "leftAt": "now"},
            {"uid": "translator-9", "leftAt": None},
        ]
        release_member.return_value = {"id": "call-1", "status": "connected", "translatorId": "translator-9"}
        response = self.client.post("/api/calls/call-1/leave")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["call"]["status"], "connected")
        self.assertTrue(response.get_json()["left"])
        mark_left.assert_called_once_with("call-1", "customer-2")
        release_member.assert_called_once_with("call-1", "customer-2")
        transition.assert_not_called()

    @patch("controllers.calls_controller.CallModel.release_member")
    @patch("controllers.calls_controller.CallModel.transition")
    @patch("controllers.calls_controller.ParticipantModel.mark_left")
    @patch("controllers.calls_controller.ParticipantModel.for_call")
    @patch("controllers.calls_controller.CallModel.is_participant", return_value=True)
    @patch("controllers.calls_controller.CallModel.get")
    @patch("controllers.calls_controller.identity_or_response")
    def test_translator_end_call_removes_only_that_translator(self, identity, get_call, _participant, for_call, mark_left, transition, release_member):
        identity.return_value = ({"uid": "translator-9", "role": "translator"}, None)
        get_call.return_value = {
            "id": "call-1", "callerId": "customer-1", "receiverId": "customer-2",
            "translatorId": "translator-9", "status": "connected",
        }
        for_call.return_value = [
            {"uid": "customer-1", "leftAt": None},
            {"uid": "customer-2", "leftAt": None},
            {"uid": "translator-9", "leftAt": "now"},
        ]
        release_member.return_value = {"id": "call-1", "status": "connected", "translatorId": None}
        response = self.client.post("/api/calls/call-1/leave")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["call"]["status"], "connected")
        mark_left.assert_called_once_with("call-1", "translator-9")
        release_member.assert_called_once_with("call-1", "translator-9")
        transition.assert_not_called()

    @patch("controllers.calls_controller.CallModel.release_member")
    @patch("controllers.calls_controller.CallModel.transition")
    @patch("controllers.calls_controller.ParticipantModel.mark_left")
    @patch("controllers.calls_controller.ParticipantModel.for_call", return_value=[
        {"uid": "customer-1", "leftAt": "now"},
        {"uid": "customer-2", "leftAt": "earlier"},
    ])
    @patch("controllers.calls_controller.CallModel.is_participant", return_value=True)
    @patch("controllers.calls_controller.CallModel.get")
    @patch("controllers.calls_controller.identity_or_response")
    def test_final_participant_leaving_ends_the_stored_call(self, identity, get_call, _participant, _for_call, mark_left, transition, release_member):
        identity.return_value = ({"uid": "customer-1", "role": "customer"}, None)
        get_call.return_value = {
            "id": "call-1", "callerId": "customer-1", "receiverId": "customer-2",
            "translatorId": None, "status": "connected",
        }
        release_member.return_value = get_call.return_value
        transition.return_value = {"id": "call-1", "status": "ended"}
        response = self.client.post("/api/calls/call-1/leave")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["call"]["status"], "ended")
        mark_left.assert_called_once_with("call-1", "customer-1")
        transition.assert_called_once_with("call-1", "ended")

    @patch("controllers.calls_controller.TranslatorModel.get", return_value={"id": "translator-9"})
    @patch("controllers.calls_controller.CallModel.all")
    @patch("controllers.calls_controller.identity_or_response")
    def test_pending_listener_shows_a_direct_invite_only_to_that_translator(self, identity, all_calls, _get_translator):
        calls = [
            {"id": "direct-chat", "purpose": "translator_chat", "status": "ringing",
             "receiverId": "translator-9", "callerName": "Grace"},
            {"id": "direct", "translationStatus": "requested", "status": "connected", "translatorId": None,
             "invitedTranslatorId": "translator-9", "callerName": "Ada"},
            {"id": "other-person", "translationStatus": "requested", "status": "connected", "translatorId": None,
             "invitedTranslatorId": "translator-2"},
            {"id": "open", "translationStatus": "requested", "status": "connected", "translatorId": None},
        ]
        all_calls.return_value = calls
        identity.return_value = ({"uid": "translator-9", "role": "translator"}, None)
        chosen = self.client.get("/api/calls/pending")
        self.assertEqual(chosen.status_code, 200)
        self.assertEqual([call["id"] for call in chosen.get_json()["calls"]], ["direct-chat", "direct"])
        identity.return_value = ({"uid": "translator-2", "role": "translator"}, None)
        other = self.client.get("/api/calls/pending")
        self.assertEqual([call["id"] for call in other.get_json()["calls"]], ["other-person"])

    @patch("controllers.calls_controller.CallModel.is_participant", return_value=False)
    @patch("controllers.calls_controller.CallModel.get")
    @patch("controllers.calls_controller.identity_or_response")
    def test_invited_translator_can_open_the_call_before_accepting(self, identity, get_call, _participant):
        get_call.return_value = {
            "id": "call-1", "callerId": "customer-1", "callerName": "Ada", "status": "connected",
            "translationStatus": "requested", "translatorId": None, "invitedTranslatorId": "translator-9",
        }
        identity.return_value = ({"uid": "translator-9", "role": "translator"}, None)
        allowed = self.client.get("/api/calls/call-1")
        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(allowed.get_json()["call"]["callerName"], "Ada")
        identity.return_value = ({"uid": "translator-2", "role": "translator"}, None)
        denied = self.client.get("/api/calls/call-1")
        self.assertEqual(denied.status_code, 404)


if __name__ == "__main__":
    unittest.main()
