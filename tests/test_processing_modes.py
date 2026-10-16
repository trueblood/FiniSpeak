import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from app import create_app
from services.audio_processing_service import AudioProcessingPipeline
from services.processing_mode_service import allowed_processing_modes, authorize_processing_mode


TRANSCRIPTION_RESULT = {
    "text": "Logged speech",
    "language": "en",
    "languageConfidence": 0.95,
}


class ProcessingModeAuthorizationTests(unittest.TestCase):
    def test_ordinary_users_only_receive_baseline(self):
        with patch.dict("os.environ", {"FINISPEAK_PROCESSING_TESTER_UIDS": "tester-1"}, clear=False):
            self.assertEqual(allowed_processing_modes({"uid": "ordinary-user"}), ["baseline"])
            with self.assertRaises(PermissionError):
                authorize_processing_mode({"uid": "ordinary-user"}, "concurrent")

    def test_authorized_testers_receive_all_modes(self):
        with patch.dict("os.environ", {"FINISPEAK_PROCESSING_TESTER_UIDS": "tester-1"}, clear=False):
            self.assertEqual(
                allowed_processing_modes({"uid": "tester-1"}),
                ["baseline", "concurrent", "streaming"],
            )


class AudioProcessingPipelineTests(unittest.TestCase):
    @patch("services.audio_processing_service.transcribe_pcm", return_value=TRANSCRIPTION_RESULT)
    def test_baseline_processes_audio_inline(self, transcribe_pcm):
        pipeline = AudioProcessingPipeline("baseline", 16000, generation=7)
        events = pipeline.feed(b"\x00" * pipeline.target_bytes)
        final = next(event for event in events if event["type"] == "final")
        self.assertEqual(final["processingMode"], "baseline")
        self.assertEqual(final["segmentId"], "7-0")
        transcribe_pcm.assert_called_once()
        pipeline.close()

    def test_concurrent_capture_does_not_wait_for_transcription(self):
        release_worker = threading.Event()

        def delayed_transcription(*_args):
            release_worker.wait(2)
            return TRANSCRIPTION_RESULT

        with patch("services.audio_processing_service.transcribe_pcm", side_effect=delayed_transcription):
            pipeline = AudioProcessingPipeline("concurrent", 16000, generation=8)
            started = time.perf_counter()
            events = pipeline.feed(b"\x00" * pipeline.target_bytes)
            elapsed = time.perf_counter() - started
            self.assertLess(elapsed, 0.5)
            self.assertEqual(events[0]["type"], "processing")
            release_worker.set()
            final = next(event for event in pipeline.finish() if event["type"] == "final")
            self.assertEqual(final["processingMode"], "concurrent")
            pipeline.close()

    @patch("services.audio_processing_service.transcribe_pcm", return_value=TRANSCRIPTION_RESULT)
    def test_streaming_uses_short_incremental_chunks(self, transcribe_pcm):
        with patch.dict("os.environ", {"STREAMING_TRANSCRIPTION_CHUNK_SECONDS": "0.5"}, clear=False):
            pipeline = AudioProcessingPipeline("streaming", 16000, generation=9)
            events = pipeline.feed(b"\x00" * pipeline.target_bytes)
            events.extend(pipeline.finish())
        final = next(event for event in events if event["type"] == "final")
        self.assertEqual(pipeline.chunk_seconds, 0.5)
        self.assertEqual(final["processingMode"], "streaming")
        transcribe_pcm.assert_called_once()
        pipeline.close()


class ProcessingModeControllerTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    @patch("controllers.calls_controller.identity_or_response")
    def test_capabilities_hide_experiments_from_ordinary_users(self, identity):
        identity.return_value = ({"uid": "ordinary-user", "role": "customer"}, None)
        with patch.dict("os.environ", {"FINISPEAK_PROCESSING_TESTER_UIDS": "tester-1"}, clear=False):
            response = self.client.get("/api/calls/processing-capabilities")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["modes"], ["baseline"])
        self.assertFalse(response.get_json()["experimental"])

    @patch("controllers.calls_controller.CallModel.set_processing_mode")
    @patch("controllers.calls_controller.identity_or_response")
    def test_mode_change_is_scoped_to_requesting_participant(self, identity, set_mode):
        identity.return_value = ({"uid": "tester-1", "role": "customer"}, None)
        set_mode.return_value = {"id": "call-1", "processingModes": {"tester-1": "streaming"}}
        with patch.dict("os.environ", {"FINISPEAK_PROCESSING_TESTER_UIDS": "tester-1"}, clear=False):
            response = self.client.patch(
                "/api/calls/call-1/processing-mode",
                json={"processingMode": "streaming"},
            )
        self.assertEqual(response.status_code, 200)
        set_mode.assert_called_once_with("call-1", "tester-1", "streaming")


class ProcessingModeBrowserContractTests(unittest.TestCase):
    def test_live_switch_keeps_media_capture_and_webrtc_intact(self):
        script = (Path(__file__).parents[1] / "views/static/js/app.js").read_text()
        switch = script[script.index("async function switchProcessingMode"):
                        script.index("async function handleProcessingFailure")]
        self.assertIn("requestPipelineStop()", switch)
        self.assertIn('processingMode:next', switch)
        self.assertIn('openTranscriptionPipeline(activeCallId,next)', switch)
        self.assertNotIn("stopTranscription(", switch)
        self.assertNotIn("localStream", switch)
        self.assertNotIn("peerConnections", switch)

    def test_switch_buffers_audio_and_uses_generation_scoped_ids(self):
        script = (Path(__file__).parents[1] / "views/static/js/app.js").read_text()
        self.assertIn("if(transcriptionSwitching||!transcriptionSocket", script)
        self.assertIn("flushTranscriptionAudio()", script)
        self.assertIn("generation===transcriptionGeneration", script)
        self.assertIn('`${currentUser.uid}-${generation}-${m.sequence??0}`', script)


if __name__ == "__main__":
    unittest.main()
