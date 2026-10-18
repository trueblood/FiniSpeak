import json
import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from services.camera_relay import HEARTBEAT_SECONDS, CameraRelay, _load_current_call, handle_camera_socket, pack_frame


JPEG = b"\xff\xd8\xff" + (b"\x00" * 32) + b"\xff\xd9"


class FakeSocket:
    def __init__(self, messages):
        self.messages = list(messages)
        self.sent = []
        self.connected = True

    def receive(self, timeout=None):
        if self.messages:
            return self.messages.pop(0)
        self.connected = False
        return None

    def send(self, message):
        self.sent.append(message)


def parse_frame(frame):
    length = frame[3]
    return frame[4:4 + length].decode(), frame[4 + length:]


class CameraRelayTests(unittest.TestCase):
    def test_relay_heartbeat_stays_below_the_proxy_idle_timeout(self):
        self.assertLess(HEARTBEAT_SECONDS, 75)

    def test_live_membership_read_ends_the_old_mysql_snapshot(self):
        calls = Mock()
        calls.get.return_value = {"id": "call-1", "translatorId": "late-translator"}
        with patch("services.camera_relay.get_repository", return_value=calls), \
                patch("services.camera_relay.db.session.rollback") as rollback:
            call = _load_current_call("call-1")
        rollback.assert_called_once_with()
        self.assertEqual(call["translatorId"], "late-translator")

    def test_frames_cross_worker_processes_and_expire(self):
        with tempfile.TemporaryDirectory() as root:
            sender = CameraRelay(root)
            receiver = CameraRelay(root)
            self.assertTrue(sender.publish("call-1", "remote-user", JPEG))
            self.assertFalse(sender.publish("call-1", "remote-user", JPEG))
            self.assertFalse(sender.publish("call-1", "remote-user", b"not-a-jpeg"))
            frame = receiver.read_since("call-1", "remote-user", 0)
            self.assertIsNotNone(frame)
            self.assertEqual(frame[1], JPEG)
            self.assertIsNone(receiver.read_since("call-1", "remote-user", frame[0]))
            path = next(Path(root).rglob("*.jpg"))
            old = time.time() - 10
            os.utime(path, (old, old))
            later = CameraRelay(root)
            self.assertIsNone(later.read_since("call-1", "remote-user", 0))

    def test_camera_off_clears_the_picture_other_workers_would_read(self):
        with tempfile.TemporaryDirectory() as root:
            relay = CameraRelay(root)
            relay.publish("call-1", "remote-user", JPEG)
            relay.clear("call-1", "remote-user")
            self.assertIsNone(CameraRelay(root).read_since("call-1", "remote-user", 0))

    def test_socket_relays_the_other_person_and_hides_your_own_frame(self):
        with tempfile.TemporaryDirectory() as root:
            relay = CameraRelay(root)
            relay.publish("call-1", "remote-user", JPEG)
            relay.publish("call-1", "local-user", JPEG)
            socket = FakeSocket([json.dumps({"type": "join", "callId": "call-1"})])
            handle_camera_socket(
                socket,
                hub=relay,
                authenticate=lambda: {"uid": "local-user"},
                load_call=lambda call_id: {
                    "callerId": "local-user",
                    "receiverId": "remote-user",
                    "status": "active",
                },
            )
            ready = json.loads(socket.sent[0])
            self.assertEqual(ready["type"], "ready")
            pictures = [message for message in socket.sent if isinstance(message, bytes)]
            self.assertEqual(len(pictures), 1)
            uid, jpeg = parse_frame(pictures[0])
            self.assertEqual(uid, "remote-user")
            self.assertEqual(jpeg, JPEG)
            self.assertEqual(pack_frame(uid, jpeg), pictures[0])

    def test_socket_rejects_someone_outside_the_call(self):
        with tempfile.TemporaryDirectory() as root:
            socket = FakeSocket([json.dumps({"type": "join", "callId": "call-1"})])
            handle_camera_socket(
                socket,
                hub=CameraRelay(root),
                authenticate=lambda: {"uid": "local-user"},
                load_call=lambda call_id: None,
            )
            self.assertEqual(json.loads(socket.sent[-1])["type"], "error")

    def test_browser_can_read_the_relay_header(self):
        frame = pack_frame("remote-user", JPEG)
        encoded = ",".join(str(byte) for byte in frame)
        result = subprocess.run(
            ["node", "--input-type=module", "-e", f"""
                import {{ parseRelayFrame, cameraCaptureSize, createCameraRelay }} from './views/static/js/camera-relay.js';
                const parsed = parseRelayFrame(new Uint8Array([{encoded}]));
                if (!parsed || parsed.uid !== 'remote-user') throw new Error('uid');
                if (parsed.jpeg[0] !== 0xff || parsed.jpeg[1] !== 0xd8) throw new Error('jpeg');
                const size = cameraCaptureSize(1920, 1080);
                if (size.width !== 640 || size.height !== 360) throw new Error('size');
                if (parseRelayFrame(new Uint8Array([1, 2, 3, 4]))) throw new Error('bad frame');
                if (!createCameraRelay.toString().includes('reconnect: reconnectNow')) throw new Error('reconnect');
            """],
            cwd=Path(__file__).parents[1],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
