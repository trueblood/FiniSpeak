import json
import unittest
from unittest.mock import patch


class FakeSocket:
    def __init__(self, messages):
        self.messages = iter(messages)
        self.sent = []

    def receive(self):
        return next(self.messages, None)

    def send(self, message):
        self.sent.append(json.loads(message))


class TranscriptionControllerTests(unittest.TestCase):
    @patch("controllers.transcription_controller.record_language_event")
    @patch("controllers.transcription_controller.transcribe_pcm")
    @patch("controllers.transcription_controller.verify_participant")
    def test_confirmed_language_updates_live_transcription(self, verify_participant, transcribe_pcm, record_language_event):
        from controllers.transcription_controller import handle_socket

        transcribe_pcm.return_value = {
            "text": "Hola",
            "language": "es",
            "languageConfidence": 1.0,
        }
        socket = FakeSocket([
            json.dumps({"type": "start", "token": "token", "callId": "call", "sampleRate": 16000}),
            json.dumps({"type": "language", "language": "es"}),
            b"\x00" * 3200,
            json.dumps({"type": "stop"}),
        ])

        handle_socket(socket)

        verify_participant.assert_called_once_with("token", "call")
        transcribe_pcm.assert_called_once_with(b"\x00" * 3200, 16000, "es", 1.0)
        self.assertEqual(socket.sent[-1]["language"], "es")
        self.assertEqual(socket.sent[-1]["languageConfidence"], 1.0)


if __name__ == "__main__":
    unittest.main()
