import os
import unittest
import wave
from types import SimpleNamespace
from unittest.mock import patch


class TranscriptionServiceTests(unittest.TestCase):
    def test_pcm_is_wrapped_as_mono_pcm16_wav(self):
        from services.transcription_service import pcm16_wav_file

        audio = pcm16_wav_file(b"\x01\x00" * 8000, 16000)
        with wave.open(audio, "rb") as wav:
            self.assertEqual(wav.getnchannels(), 1)
            self.assertEqual(wav.getsampwidth(), 2)
            self.assertEqual(wav.getframerate(), 16000)
            self.assertEqual(wav.getnframes(), 8000)

    @patch("services.transcription_service._get_client")
    def test_gpt_transcribe_returns_text_and_detected_language(self, get_client):
        from services.transcription_service import transcribe_pcm

        create = get_client.return_value.audio.transcriptions.create
        create.return_value = SimpleNamespace(
            text="Hola, ¿cómo está?",
            languages=[SimpleNamespace(code="es", confidence=0.91)],
        )
        with patch.dict(os.environ, {"OPENAI_TRANSCRIPTION_MODEL": "gpt-transcribe"}, clear=False):
            result = transcribe_pcm(b"\x00\x00" * 8000, 16000)

        self.assertEqual(result, {"text": "Hola, ¿cómo está?", "language": "es", "languageConfidence": 0.91})
        request = create.call_args.kwargs
        self.assertEqual(request["model"], "gpt-transcribe")
        self.assertEqual(request["file"].name, "finispeak-audio.wav")
        self.assertIn("FiniSpeak", request["extra_body"]["keywords"])

    def test_short_audio_does_not_call_api(self):
        from services.transcription_service import transcribe_pcm

        with patch("services.transcription_service._get_client") as get_client:
            result = transcribe_pcm(b"\x00\x00" * 100, 16000, "en")
        self.assertEqual(result, {"text": "", "language": "en", "languageConfidence": None})
        get_client.assert_not_called()

    @patch("services.transcription_service._get_client")
    def test_missing_metadata_confidence_uses_classifier_score(self, get_client):
        from services.transcription_service import transcribe_pcm

        get_client.return_value.audio.transcriptions.create.return_value = SimpleNamespace(
            text="This is clearly an English sentence.",
            languages=[SimpleNamespace(code="en")],
        )
        get_client.return_value.responses.create.return_value = SimpleNamespace(
            output_text='{"language":"en","confidence":0.97}'
        )

        result = transcribe_pcm(b"\x00\x00" * 8000, 16000)

        self.assertEqual(result["language"], "en")
        self.assertEqual(result["languageConfidence"], 0.97)

    @patch("services.transcription_service._get_client")
    def test_language_falls_back_to_text_classifier(self, get_client):
        from services.transcription_service import transcribe_pcm

        get_client.return_value.audio.transcriptions.create.return_value = SimpleNamespace(text="Bonjour tout le monde")
        get_client.return_value.responses.create.return_value = SimpleNamespace(
            output_text='{"language":"fr","confidence":0.93}'
        )

        result = transcribe_pcm(b"\x00\x00" * 8000, 16000)

        self.assertEqual(result["language"], "fr")
        self.assertEqual(result["languageConfidence"], 0.93)


if __name__ == "__main__":
    unittest.main()
