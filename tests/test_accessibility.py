import subprocess
import unittest
from html.parser import HTMLParser
from pathlib import Path


TEMPLATE = Path(__file__).parents[1] / "views" / "templates" / "index.html"


class AccessibilityParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = set()
        self.labels = []
        self.controls = []
        self.dialogs = []
        self.html_lang = None

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if values.get("id"):
            self.ids.add(values["id"])
        if tag == "html":
            self.html_lang = values.get("lang")
        if tag == "label" and values.get("for"):
            self.labels.append(values["for"])
        if tag in {"input", "select", "textarea"} and values.get("id"):
            self.controls.append((values["id"], values))
        if values.get("role") == "dialog":
            self.dialogs.append(values)


class AccessibilityRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = TEMPLATE.read_text()
        cls.parser = AccessibilityParser()
        cls.parser.feed(cls.html)

    def test_document_language_and_skip_link(self):
        self.assertEqual(self.parser.html_lang, "en")
        self.assertIn('class="skip-link" href="#mainContent"', self.html)

    def test_explicit_labels_reference_real_controls(self):
        self.assertTrue(set(self.parser.labels).issubset(self.parser.ids))

    def test_modals_have_names_and_hidden_state(self):
        self.assertGreaterEqual(len(self.parser.dialogs), 4)
        for dialog in self.parser.dialogs:
            self.assertEqual(dialog.get("aria-modal"), "true")
            self.assertEqual(dialog.get("aria-hidden"), "true")
            self.assertIn(dialog.get("aria-labelledby"), self.parser.ids)

    def test_call_controls_expose_toggle_state(self):
        self.assertIn('id="muteButton" class="secondary" type="button" aria-pressed="false"', self.html)
        self.assertIn('id="cameraButton" class="secondary" type="button" aria-pressed="false"', self.html)

    def test_call_stage_keeps_interpreter_and_participant_grid(self):
        self.assertLess(self.html.index('id="smartInterpreter"'), self.html.index('class="call-nav"'))
        self.assertIn('id="smartInterpreterWave"', self.html)
        self.assertIn("Smart Interpreter", self.html)
        self.assertIn('id="smartInterpreter" class="smart-interpreter" hidden aria-hidden="true"', self.html)
        self.assertIn('id="participantGrid" class="participant-grid" hidden', self.html)
        self.assertIn('id="transcriptList" class="transcript-list" role="log"', self.html)
        script = (Path(__file__).parents[1] / "views/static/js/call-experience.js").read_text()
        styles = (Path(__file__).parents[1] / "views/static/css/call.css").read_text()
        layout = script[script.index("function layout()"):script.index("function setInterpreterActivity")]
        self.assertIn("cameraGridShape", script)
        self.assertIn("stage.appendChild(card)", layout)
        self.assertNotIn("? stage : film", layout)
        self.assertIn("--camera-columns", layout)
        self.assertIn("--camera-rows", layout)
        self.assertIn("grid-template-columns:repeat(var(--camera-columns, 1), minmax(0, 1fr))", styles)
        self.assertIn("grid-template-rows:repeat(var(--camera-rows, 1), minmax(0, 1fr))", styles)
        self.assertIn("grid-template-columns:repeat(auto-fit,minmax(min(240px,100%),1fr))", styles)
        self.assertIn("position:absolute; left:50%; bottom:18px", styles)
        self.assertIn(".call-shell.is-transcript-collapsed .floating-controls { margin-left:0; }", styles)
        self.assertIn('id="toggleCallControls"', self.html)
        self.assertIn('id="callControls" class="call-controls floating-controls"', self.html)
        self.assertIn('class="call-shell subs-both is-transcript-collapsed"', self.html)
        self.assertIn('class="call-control-more"', self.html)
        self.assertLess(self.html.index('id="expandTranscript"'), self.html.index('class="call-nav-meta"'))
        self.assertIn('setTranscriptCollapsed(true)', script)
        self.assertIn("is-mobile-pair", layout)
        self.assertIn("gridTemplateColumns", layout)
        self.assertNotIn("is-zoom-speaker", layout)
        self.assertIn("is-controls-collapsed", styles)
        self.assertIn(".is-mobile-pair", styles)
        self.assertIn('id="callRoster"', self.html)
        self.assertIn('id="callRosterList"', self.html)
        app = (Path(__file__).parents[1] / "views/static/js/app.js").read_text()
        mesh = (Path(__file__).parents[1] / "views/static/js/webrtc-mesh.js").read_text()
        peers = app[app.index("async function ensurePeer"):app.index("function connectSignaling")]
        presence = script[script.index("function applyParticipantPresence"):script.index("function cameraGridShape")]
        self.assertIn("function ensureParticipantTile", app)
        self.assertIn("function attachRemoteTrack", app)
        self.assertIn("function peopleInCall", app)
        self.assertIn("nextMembershipKey !== callMembershipKey", app)
        self.assertIn("cameraRelay?.reconnect?.()", app)
        self.assertIn('callMembershipKey = ""', app)
        self.assertIn("callerId", app[app.index("function peopleInCall"):app.index("function peopleInCall") + 700])
        self.assertIn("have-local-offer", peers)
        self.assertIn("isOfferer", peers)
        self.assertIn("shouldSendOffer", peers)
        self.assertIn("_suppressOffer", peers)
        self.assertIn("onnegotiationneeded", mesh)
        self.assertIn("function shouldSendOffer", mesh)
        self.assertIn("if (!pc._offerer || pc._suppressOffer) return;", mesh)
        self.assertNotIn("pc._offerer === false", mesh)
        self.assertIn("rollback", mesh)
        self.assertIn("function isOfferer", mesh)
        self.assertIn("function offerResponse", mesh)
        negotiated = subprocess.run(
            ["node", "--input-type=module", "-e", """
                import { isOfferer, offerResponse, shouldForceRelay, shouldSendOffer } from './views/static/js/webrtc-mesh.js';
                if (!isOfferer('a', 'b') || isOfferer('b', 'a')) throw new Error('offerer');
                if (offerResponse('have-local-offer', { offerer: true }) !== 'ignore') throw new Error('offerer waits');
                if (offerResponse('have-local-offer', { offerer: false }) !== 'rollback') throw new Error('answerer yields');
                if (offerResponse('stable', { offerer: false }) !== 'answer') throw new Error('stable answers');
                if (offerResponse('closed', { offerer: false }) !== 'restart') throw new Error('bad state restarts');
                if (shouldSendOffer({ offerer: true, signalingState: 'stable', waitedMs: 0 }) !== 'offer') throw new Error('offerer starts');
                if (shouldSendOffer({ offerer: false, signalingState: 'stable', waitedMs: 0 }) !== 'wait') throw new Error('answerer waits');
                if (shouldSendOffer({ offerer: false, signalingState: 'stable', waitedMs: 4000 }) !== 'offer') throw new Error('answerer fallback');
                if (shouldSendOffer({ offerer: true, signalingState: 'have-local-offer' }) !== 'resend') throw new Error('offerer resends');
                if (shouldSendOffer({ offerer: false, signalingState: 'have-local-offer' }) !== 'wait') throw new Error('answerer does not glare');
                if (shouldSendOffer({ offerer: true, signalingState: 'stable', hasRemote: true }) !== 'wait') throw new Error('settled waits');
                if (shouldSendOffer({ offerer: true, signalingState: 'stable', connected: true }) !== 'wait') throw new Error('connected waits');
                if (!shouldForceRelay({ relayAvailable: true, waitedMs: 10000 })) throw new Error('stalled peer uses turn');
                if (!shouldForceRelay({ relayAvailable: true, disconnectedMs: 5000 })) throw new Error('disconnected peer uses turn');
                if (shouldForceRelay({ relayAvailable: false, waitedMs: 20000 })) throw new Error('turn must exist');
                if (shouldForceRelay({ relayAvailable: true, forceRelay: true, waitedMs: 20000 })) throw new Error('relay retries stay bounded');
                if (shouldForceRelay({ relayAvailable: true, connected: true, waitedMs: 20000 })) throw new Error('connected peer stays put');
            """],
            cwd=Path(__file__).parents[1],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        self.assertEqual(negotiated.returncode, 0, negotiated.stderr)
        self.assertIn("event.track", mesh)
        self.assertNotIn("e.streams[0]", mesh)
        self.assertIn('track.readyState === "live"', presence)
        self.assertNotIn("track.muted === false", presence)

    def test_transcripts_are_named_logs(self):
        self.assertIn('id="transcriptList" class="transcript-list" role="log"', self.html)
        self.assertIn('id="historyTranscriptList" class="transcript-list history-transcript-list" role="log"', self.html)

    def test_experimental_processing_controls_are_hidden_and_stateful(self):
        self.assertNotIn('id="preCallProcessingModes"', self.html)
        self.assertIn('id="callProcessingModes" class="processing-mode-panel call-processing-modes hidden"', self.html)
        self.assertEqual(self.html.count('data-processing-mode="baseline" aria-pressed="false"'), 1)
        self.assertEqual(self.html.count('data-processing-mode="concurrent" aria-pressed="false"'), 1)
        self.assertEqual(self.html.count('data-processing-mode="streaming" aria-pressed="false"'), 1)

    def test_sign_language_option_is_a_placeholder_dialog(self):
        self.assertIn('id="signAccessButton" class="secondary" type="button"', self.html)
        self.assertIn('id="signAccessModal" class="modal-backdrop hidden" role="dialog" aria-modal="true" aria-hidden="true" aria-labelledby="signAccessTitle"', self.html)
        self.assertIn('id="signNetNotesTitle">FiniSpeak SignNet v1', self.html)
        self.assertIn('id="signNetArchitectureTitle">Our simplified AI architecture', self.html)
        self.assertIn("FiniSpeak SignNet v0.1", self.html)
        self.assertIn("MediaPipe Hands", self.html)
        self.assertIn("21 landmarks per hand", self.html)
        self.assertIn("Speech text + recognized hand signs", self.html)
        self.assertIn("this window does not read the camera or microphone", self.html)

    def test_mobile_translator_request_leads_with_matches(self):
        self.assertIn('id="requestBestMatchList"', self.html)
        self.assertIn('id="requestLanguageSearchPanel" class="request-search-disclosure" open', self.html)
        self.assertIn(">More translators<", self.html)
        self.assertIn(">Map options<", self.html)
        self.assertIn('id="requestMatchMapButton"', self.html)
        self.assertIn(">Top matches<", self.html)
        self.assertIn('id="requestMatchHint"', self.html)
        script = (Path(__file__).parents[1] / "views/static/js/app.js").read_text()
        styles = (Path(__file__).parents[1] / "views/static/css/style.css").read_text()
        opener = script[script.index("function openTranslatorRequest"):script.index("async function loadAvailableRequestMatches")]
        self.assertIn("loadAvailableRequestMatches()", opener)
        self.assertNotIn("if (mobile) loadAvailableRequestMatches()", opener)
        self.assertIn("matches.slice(0, 3)", script)
        self.assertIn(".request-best-matches { display:block;", styles)
        self.assertNotIn(".request-best-matches,.request-map-options { display:none; }", styles)

    def test_every_phone_input_has_a_country_code_selector(self):
        self.assertEqual(self.html.count('type="tel"'), 5)
        self.assertEqual(self.html.count('data-phone-country'), 5)
        for prefix in ("signupPhone", "receiverPhone", "friendPhone", "profilePhone", "interpreterPhone"):
            self.assertIn(f'id="{prefix}Country"', self.html)
            self.assertIn(f'id="{prefix}" type="tel"', self.html)


if __name__ == "__main__":
    unittest.main()
