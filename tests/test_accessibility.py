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
        self.assertIn('id="smartInterpreter" class="smart-interpreter" aria-label="Smart Interpreter"', self.html)
        self.assertIn('id="participantGrid" class="participant-grid" hidden', self.html)
        self.assertIn('id="transcriptList" class="transcript-list" role="log"', self.html)

    def test_transcripts_are_named_logs(self):
        self.assertIn('id="transcriptList" class="transcript-list" role="log"', self.html)
        self.assertIn('id="historyTranscriptList" class="transcript-list history-transcript-list" role="log"', self.html)

    def test_experimental_processing_controls_are_hidden_and_stateful(self):
        self.assertNotIn('id="preCallProcessingModes"', self.html)
        self.assertIn('id="callProcessingModes" class="processing-mode-panel call-processing-modes hidden"', self.html)
        self.assertEqual(self.html.count('data-processing-mode="baseline" aria-pressed="false"'), 1)
        self.assertEqual(self.html.count('data-processing-mode="concurrent" aria-pressed="false"'), 1)
        self.assertEqual(self.html.count('data-processing-mode="streaming" aria-pressed="false"'), 1)

    def test_every_phone_input_has_a_country_code_selector(self):
        self.assertEqual(self.html.count('type="tel"'), 5)
        self.assertEqual(self.html.count('data-phone-country'), 5)
        for prefix in ("signupPhone", "receiverPhone", "friendPhone", "profilePhone", "interpreterPhone"):
            self.assertIn(f'id="{prefix}Country"', self.html)
            self.assertIn(f'id="{prefix}" type="tel"', self.html)


if __name__ == "__main__":
    unittest.main()
