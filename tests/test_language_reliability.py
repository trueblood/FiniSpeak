import unittest

from services.language_evaluation_service import evaluate_language_predictions, release_gate
from services.language_reliability_service import LanguageEvidenceTracker


class LanguageReliabilityTests(unittest.TestCase):
    def test_multiple_samples_stabilize_high_confidence_language(self):
        tracker = LanguageEvidenceTracker(window_size=5, confirmation_threshold=0.7, minimum_samples=2)
        first = tracker.add("es", 0.9, 60)
        second = tracker.add("es-MX", 0.92, 80)
        self.assertTrue(first["requiresConfirmation"])
        self.assertEqual(second["primaryLanguage"], "es")
        self.assertFalse(second["requiresConfirmation"])

    def test_conflicting_samples_require_confirmation(self):
        tracker = LanguageEvidenceTracker(window_size=4, confirmation_threshold=0.78, minimum_samples=2)
        tracker.add("es", 0.9, 60)
        result = tracker.add("fr", 0.9, 60)
        self.assertTrue(result["requiresConfirmation"])
        self.assertTrue(result["alternatives"])

    def test_user_confirmation_is_authoritative(self):
        tracker = LanguageEvidenceTracker()
        tracker.add("es", 0.6, 20)
        result = tracker.confirm("fr")
        self.assertEqual(result["primaryLanguage"], "fr")
        self.assertEqual(result["primaryConfidence"], 1.0)
        self.assertFalse(result["requiresConfirmation"])

    def test_release_gate_rejects_low_accuracy(self):
        metrics = evaluate_language_predictions([
            {"expectedLanguage": "en", "predictedLanguage": "es", "confidence": 0.99, "confirmedLanguage": "en"},
            {"expectedLanguage": "fr", "predictedLanguage": "fr", "confidence": 0.99, "confirmedLanguage": "fr"},
        ])
        self.assertFalse(release_gate(metrics)["passed"])


if __name__ == "__main__":
    unittest.main()
