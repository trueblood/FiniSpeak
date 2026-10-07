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

    def test_transcripts_are_named_logs(self):
        self.assertIn('id="transcriptList" class="transcript-list" role="log"', self.html)
        self.assertIn('id="historyTranscriptList" class="transcript-list history-transcript-list" role="log"', self.html)


if __name__ == "__main__":
    unittest.main()
