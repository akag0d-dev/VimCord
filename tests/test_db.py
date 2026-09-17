"""
Unit tests for VimCord SQLite Database module (auth, history, friends, invites).
"""

import os
import tempfile
import unittest
from vimcord.server.db import Database


class TestDatabase(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp_dir.name, "test_vimcord.db")
        self.db = Database(self.db_path)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_registration_and_login(self):
        ok, msg, u1 = self.db.register_user("Alice", "password123")
        self.assertTrue(ok)
        self.assertEqual(u1["username"], "Alice")
        self.assertTrue(u1["user_id"].startswith("u-"))

        # Duplicate registration should fail
        ok2, msg2, _ = self.db.register_user("Alice", "pass456")
        self.assertFalse(ok2)

        # Login with correct password
        auth_ok, _, auth_u = self.db.authenticate_user("Alice", "password123")
        self.assertTrue(auth_ok)
        self.assertEqual(auth_u["user_id"], u1["user_id"])

        # Login with wrong password
        auth_wrong, _, _ = self.db.authenticate_user("Alice", "wrongpass")
        self.assertFalse(auth_wrong)

    def test_profile_update_and_password_change(self):
        _, _, u = self.db.register_user("Charlie", "secret123")
        uid = u["user_id"]

        # Update profile
        ok, _ = self.db.update_profile(uid, username="Charlie_Pro", status_text="Кодит на PyQt6", avatar_color="#ED4245")
        self.assertTrue(ok)

        u_updated = self.db.get_user_by_id(uid)
        self.assertEqual(u_updated["username"], "Charlie_Pro")
        self.assertEqual(u_updated["status_text"], "Кодит на PyQt6")
        self.assertEqual(u_updated["avatar_color"], "#ED4245")

        # Change password
        self.assertFalse(self.db.change_password(uid, "wrongold", "newsecret")[0])
        self.assertTrue(self.db.change_password(uid, "secret123", "newsecret")[0])
        self.assertTrue(self.db.authenticate_user("Charlie_Pro", "newsecret")[0])

    def test_persistent_messages_and_dm_canonical_key(self):
        _, _, u1 = self.db.register_user("Alice", "pass123")
        _, _, u2 = self.db.register_user("Bob", "pass123")

        dm_key = self.db.get_canonical_dm_id(u1["user_id"], u2["user_id"])
        # Should be identical regardless of argument order
        self.assertEqual(dm_key, self.db.get_canonical_dm_id(u2["user_id"], u1["user_id"]))

        # Save DM messages
        self.db.save_message("m1", "dm", dm_key, u1["user_id"], "Alice", "Привет, Боб!", 1000.0)
        self.db.save_message("m2", "dm", dm_key, u2["user_id"], "Bob", "Привет, Алиса!", 1001.0)

        history = self.db.get_messages(dm_key)
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["content"], "Привет, Боб!")
        self.assertEqual(history[1]["content"], "Привет, Алиса!")

    def test_friends_workflow(self):
        _, _, u1 = self.db.register_user("UserA", "pass123")
        _, _, u2 = self.db.register_user("UserB", "pass123")

        # A sends friend request to B
        ok, _, target = self.db.send_friend_request(u1["user_id"], "UserB")
        self.assertTrue(ok)
        self.assertEqual(target["username"], "UserB")

        # Check pending lists
        f_a = self.db.get_friends(u1["user_id"])
        f_b = self.db.get_friends(u2["user_id"])
        self.assertEqual(len(f_a), 1)
        self.assertEqual(len(f_b), 1)
        self.assertTrue(f_a[0]["is_outgoing"])
        self.assertTrue(f_b[0]["is_incoming"])

        # B accepts request
        self.assertTrue(self.db.accept_friend_request(u2["user_id"], u1["user_id"]))

        # Now both are accepted friends
        f_a_accepted = self.db.get_friends(u1["user_id"])
        self.assertEqual(f_a_accepted[0]["friendship_status"], "accepted")

    def test_room_invites(self):
        _, _, u = self.db.register_user("Admin", "pass123")
        code = self.db.create_invite("room-default", u["user_id"])
        self.assertTrue(code.startswith("VC-"))

        _, _, u2 = self.db.register_user("Member", "pass123")
        ok, _, room_id = self.db.join_by_invite(code, u2["user_id"])
        self.assertTrue(ok)
        self.assertEqual(room_id, "room-default")


if __name__ == "__main__":
    unittest.main()
