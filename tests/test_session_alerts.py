import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from app import create_app
from services.session_alerts import alert_moments


class SessionAlertTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    def test_alert_moments_mark_five_minutes_and_the_start(self):
        start = datetime(2026, 11, 20, 16, 0, tzinfo=timezone.utc)
        early = alert_moments(start, now=start - timedelta(hours=1))
        self.assertTrue(early["booked_due"])
        self.assertFalse(early["soon_due"])
        self.assertEqual(early["soon"], start - timedelta(minutes=5))
        soon = alert_moments(start, now=start - timedelta(minutes=4))
        self.assertTrue(soon["soon_due"])
        self.assertFalse(soon["start_due"])
        begun = alert_moments(start, now=start + timedelta(seconds=30))
        self.assertTrue(begun["start_due"])
        self.assertIsNone(alert_moments("not-a-date"))

    @patch("controllers.sessions_controller.SessionModel.create")
    @patch("controllers.sessions_controller.identity_or_response")
    def test_invalid_scheduled_at_is_rejected(self, identity, create_session):
        identity.return_value = ({"uid": "customer-1"}, None)
        response = self.client.post("/api/sessions", json={"language": "Spanish", "scheduledAt": "tomorrow"})
        self.assertEqual(response.status_code, 400)
        create_session.assert_not_called()

    @patch("controllers.sessions_controller.notify_session_booked")
    @patch("controllers.sessions_controller.SessionModel.create")
    @patch("controllers.sessions_controller.identity_or_response")
    def test_scheduled_session_notifies_the_translator(self, identity, create_session, notify):
        identity.return_value = ({"uid": "customer-1", "displayName": "Customer"}, None)
        create_session.return_value = {"id": "session-1", "translatorId": "translator-1", "status": "connected"}
        response = self.client.post("/api/sessions", json={
            "language": "Spanish",
            "translatorId": "translator-1",
            "scheduledAt": "2026-11-20T16:00:00Z",
        })
        self.assertEqual(response.status_code, 201)
        scheduled = create_session.call_args.kwargs["scheduled_at"]
        self.assertEqual(scheduled.year, 2026)
        self.assertEqual(scheduled.hour, 16)
        self.assertEqual(scheduled.tzinfo, timezone.utc)
        notify.assert_called_once_with({"id": "session-1", "translatorId": "translator-1", "status": "connected"})
