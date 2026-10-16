import json
import threading
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
    @patch("services.audio_processing_service.transcribe_pcm")
    @patch("controllers.transcription_controller.verify_participant")
    def test_confirmed_language_updates_live_transcription(self, verify_participant, transcribe_pcm, record_language_event):
        from controllers.transcription_controller import handle_socket

        verify_participant.return_value = {"uid": "tester-1", "role": "customer"}
        transcribe_pcm.return_value = {
            "text": "Hola",
            "language": "es",
            "languageConfidence": 1.0,
        }
        socket = FakeSocket([
            json.dumps({"type": "start", "callId": "call", "sampleRate": 16000}),
            json.dumps({"type": "language", "language": "es"}),
            b"\x00" * 3200,
            json.dumps({"type": "stop"}),
        ])

        handle_socket(socket)

        verify_participant.assert_called_once_with(None, "call")
        transcribe_pcm.assert_called_once_with(b"\x00" * 3200, 16000, "es", 1.0)
        final = next(message for message in socket.sent if message.get("type") == "final")
        self.assertEqual(final["language"], "es")
        self.assertEqual(final["languageConfidence"], 1.0)
        self.assertEqual(final["processingMode"], "baseline")
        self.assertEqual(socket.sent[-1]["type"], "stopped")

    @patch("controllers.transcription_controller.record_language_event")
    @patch("services.audio_processing_service.transcribe_pcm")
    @patch("controllers.transcription_controller.verify_participant")
    def test_experimental_buttons_select_the_requested_backend_pipeline(
        self, verify_participant, transcribe_pcm, _record_language_event
    ):
        from controllers.transcription_controller import handle_socket

        verify_participant.return_value = {"uid": "tester-1", "role": "customer"}
        transcribe_pcm.return_value = {"text": "", "language": None, "languageConfidence": None}
        with patch.dict("os.environ", {"FINISPEAK_PROCESSING_TESTER_UIDS": "tester-1"}, clear=False):
            for mode in ("concurrent", "streaming"):
                with self.subTest(mode=mode):
                    socket = FakeSocket([
                        json.dumps({
                            "type": "start",
                            "callId": "call",
                            "sampleRate": 16000,
                            "processingMode": mode,
                        }),
                        json.dumps({"type": "stop"}),
                    ])
                    handle_socket(socket)
                    self.assertEqual(socket.sent[0]["type"], "ready")
                    self.assertEqual(socket.sent[0]["processingMode"], mode)

    @patch("controllers.transcription_controller.record_language_event")
    @patch("services.audio_processing_service.transcribe_pcm")
    @patch("controllers.transcription_controller.verify_participant")
    def test_concurrent_stop_drains_processing_before_acknowledging_switch(
        self, verify_participant, transcribe_pcm, _record_language_event
    ):
        from controllers.transcription_controller import handle_socket

        verify_participant.return_value = {"uid": "tester-1", "role": "customer"}
        release_worker = threading.Event()
        def delayed_transcription(*_args):
            release_worker.wait(2)
            return {
                "text": "Buffered words",
                "language": "en",
                "languageConfidence": 0.9,
            }
        transcribe_pcm.side_effect = delayed_transcription
        socket = FakeSocket([
            json.dumps({
                "type": "start",
                "callId": "call",
                "sampleRate": 16000,
                "processingMode": "concurrent",
            }),
            b"\x00" * 160000,
            json.dumps({"type": "stop"}),
        ])
        timer = threading.Timer(0.05, release_worker.set)
        timer.start()
        try:
            with patch.dict("os.environ", {"FINISPEAK_PROCESSING_TESTER_UIDS": "tester-1"}, clear=False):
                handle_socket(socket)
        finally:
            timer.cancel()
        message_types = [message["type"] for message in socket.sent]
        self.assertIn("processing", message_types)
        self.assertLess(message_types.index("final"), message_types.index("stopped"))


if __name__ == "__main__":
    unittest.main()
