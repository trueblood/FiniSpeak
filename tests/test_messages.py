"""Direct messages and group chats between FiniSpeak accounts."""

import tempfile
import unittest
from unittest.mock import patch

from app import create_app
from extensions import db
from models.sql_models import (
    SqlAuthCredential, SqlAuthRateLimit, SqlAuthSession, SqlAuthToken, SqlConversation,
    SqlConversationMember, SqlFriend, SqlMessage, SqlUser,
)


TABLES = (
    SqlUser.__table__, SqlAuthCredential.__table__, SqlAuthSession.__table__,
    SqlAuthToken.__table__, SqlAuthRateLimit.__table__, SqlFriend.__table__,
    SqlConversation.__table__, SqlConversationMember.__table__, SqlMessage.__table__,
)


class MessageTests(unittest.TestCase):
    def setUp(self):
        self.storage = tempfile.TemporaryDirectory()
        self.app = create_app()
        self.app.config.update(TESTING=True, TEST_STORAGE_ROOT=self.storage.name)
        self.context = self.app.app_context()
        self.context.push()
        db.metadata.create_all(bind=db.engine, tables=TABLES)
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.engine.dispose()
        self.context.pop()
        self.storage.cleanup()

    def register_and_verify(self, email, name):
        with patch("controllers.auth_controller.send_account_link"):
            response = self.client.post("/api/auth/register", json={
                "email": email, "password": "CorrectHorse123", "displayName": name,
            })
        self.assertEqual(response.status_code, 201, response.get_json())
        token = response.get_json()["testToken"]
        verified = self.client.post("/api/auth/verify-email", json={"token": token})
        self.assertEqual(verified.status_code, 200, verified.get_json())
        return response.get_json()["user"]

    def login(self, email):
        response = self.client.post("/api/auth/login", json={"email": email, "password": "CorrectHorse123"})
        self.assertEqual(response.status_code, 200, response.get_json())
        return {"Authorization": f"Bearer {response.get_json()['accessToken']}"}

    def add_friend(self, headers, email):
        response = self.client.post("/api/friends", headers=headers, json={"email": email})
        self.assertEqual(response.status_code, 201, response.get_json())
        return response.get_json()["friend"]

    def test_direct_messages_are_private_and_reopen_the_same_chat(self):
        owner = self.register_and_verify("owner@example.test", "Owner")
        friend = self.register_and_verify("friend@example.test", "Friend")
        outsider = self.register_and_verify("outsider@example.test", "Outsider")
        owner_headers = self.login("owner@example.test")
        friend_headers = self.login("friend@example.test")
        outsider_headers = self.login("outsider@example.test")

        opened = self.client.post("/api/messages/conversations", headers=owner_headers, json={
            "kind": "direct", "userId": friend["uid"],
        })
        self.assertEqual(opened.status_code, 201, opened.get_json())
        conversation_id = opened.get_json()["conversation"]["id"]
        self.assertEqual(opened.get_json()["conversation"]["title"], "Friend")

        again = self.client.post("/api/messages/conversations", headers=friend_headers, json={
            "kind": "direct", "email": owner["email"],
        })
        self.assertEqual(again.status_code, 200, again.get_json())
        self.assertEqual(again.get_json()["conversation"]["id"], conversation_id)

        self.assertEqual(self.client.post("/api/messages/conversations", headers=owner_headers, json={
            "kind": "direct", "userId": owner["uid"],
        }).status_code, 400)
        empty = self.client.post(
            f"/api/messages/conversations/{conversation_id}/messages",
            headers=owner_headers, json={"body": "   "},
        )
        self.assertEqual(empty.status_code, 400)

        sent = self.client.post(
            f"/api/messages/conversations/{conversation_id}/messages",
            headers=owner_headers, json={"body": "Hello from Owner"},
        )
        self.assertEqual(sent.status_code, 201, sent.get_json())
        reply = self.client.post(
            f"/api/messages/conversations/{conversation_id}/messages",
            headers=friend_headers, json={"body": "Hello back"},
        )
        self.assertEqual(reply.status_code, 201, reply.get_json())

        friend_view = self.client.get(f"/api/messages/conversations/{conversation_id}", headers=friend_headers)
        self.assertEqual(friend_view.status_code, 200)
        bodies = [item["body"] for item in friend_view.get_json()["messages"]]
        self.assertEqual(bodies, ["Hello from Owner", "Hello back"])
        self.assertEqual(friend_view.get_json()["conversation"]["unreadCount"], 0)

        inbox = self.client.get("/api/messages/conversations", headers=owner_headers)
        self.assertEqual(inbox.status_code, 200)
        self.assertEqual(inbox.get_json()["conversations"][0]["lastMessage"]["body"], "Hello back")
        self.assertEqual(inbox.get_json()["conversations"][0]["unreadCount"], 1)

        hidden = self.client.get(f"/api/messages/conversations/{conversation_id}", headers=outsider_headers)
        self.assertEqual(hidden.status_code, 404)
        blocked = self.client.post(
            f"/api/messages/conversations/{conversation_id}/messages",
            headers=outsider_headers, json={"body": "I should not be here"},
        )
        self.assertEqual(blocked.status_code, 404)

    def test_groups_are_limited_to_friends_and_current_members(self):
        owner = self.register_and_verify("group-owner@example.test", "Group Owner")
        first = self.register_and_verify("group-one@example.test", "Group One")
        second = self.register_and_verify("group-two@example.test", "Group Two")
        stranger = self.register_and_verify("stranger@example.test", "Stranger")
        owner_headers = self.login("group-owner@example.test")
        first_headers = self.login("group-one@example.test")
        second_headers = self.login("group-two@example.test")
        self.add_friend(owner_headers, first["email"])
        self.add_friend(owner_headers, second["email"])

        rejected = self.client.post("/api/messages/conversations", headers=owner_headers, json={
            "kind": "group", "title": "Project", "memberIds": [stranger["uid"]],
        })
        self.assertEqual(rejected.status_code, 400)
        self.assertIn("friend", rejected.get_json()["error"])

        created = self.client.post("/api/messages/conversations", headers=owner_headers, json={
            "kind": "group", "title": "  Project  ", "memberIds": [first["uid"], first["uid"]],
        })
        self.assertEqual(created.status_code, 201, created.get_json())
        conversation = created.get_json()["conversation"]
        self.assertEqual(conversation["title"], "Project")
        self.assertEqual(conversation["memberCount"], 2)
        conversation_id = conversation["id"]

        denied = self.client.post(
            f"/api/messages/conversations/{conversation_id}/members",
            headers=first_headers, json={"userId": second["uid"]},
        )
        self.assertEqual(denied.status_code, 400)

        added = self.client.post(
            f"/api/messages/conversations/{conversation_id}/members",
            headers=owner_headers, json={"userId": second["uid"]},
        )
        self.assertEqual(added.status_code, 200, added.get_json())
        self.assertEqual(added.get_json()["conversation"]["memberCount"], 3)

        posted = self.client.post(
            f"/api/messages/conversations/{conversation_id}/messages",
            headers=second_headers, json={"body": "I am in the group"},
        )
        self.assertEqual(posted.status_code, 201, posted.get_json())

        removed = self.client.delete(
            f"/api/messages/conversations/{conversation_id}/members/{second['uid']}",
            headers=owner_headers,
        )
        self.assertEqual(removed.status_code, 200, removed.get_json())
        self.assertEqual(removed.get_json()["conversation"]["memberCount"], 2)
        self.assertEqual(self.client.get(
            f"/api/messages/conversations/{conversation_id}", headers=second_headers,
        ).status_code, 404)

        owner_left = self.client.delete(
            f"/api/messages/conversations/{conversation_id}/members/{owner['uid']}",
            headers=owner_headers,
        )
        self.assertEqual(owner_left.status_code, 200, owner_left.get_json())
        self.assertTrue(owner_left.get_json()["left"])
        promoted = self.client.get(f"/api/messages/conversations/{conversation_id}", headers=first_headers)
        self.assertEqual(promoted.status_code, 200, promoted.get_json())
        self.assertEqual(promoted.get_json()["conversation"]["viewerRole"], "owner")
        self.assertEqual(
            [message["body"] for message in promoted.get_json()["messages"]],
            ["I am in the group"],
        )

        left = self.client.delete(
            f"/api/messages/conversations/{conversation_id}/members/{first['uid']}",
            headers=first_headers,
        )
        self.assertEqual(left.status_code, 200, left.get_json())
        self.assertTrue(left.get_json()["left"])
        self.assertEqual(self.client.post(
            f"/api/messages/conversations/{conversation_id}/messages",
            headers=first_headers, json={"body": "Still here?"},
        ).status_code, 404)
        self.assertEqual(self.client.get(
            f"/api/messages/conversations/{conversation_id}", headers=owner_headers,
        ).status_code, 404)


if __name__ == "__main__":
    unittest.main()
