"""
Unit and integration tests for VimCord v0.4.0 features and bug fixes.
"""
import asyncio
import base64
import os
import tempfile
import unittest
from pathlib import Path

from vimcord.server.db import Database
from vimcord.server.server_state import ServerState
from vimcord.server.tcp_server import TCPServer
from vimcord.common.protocol import encode_json_message, decode_json_message
from vimcord.client.config import load_client_config, save_client_config, clear_auto_login


class TestConfigAppData(unittest.TestCase):
    def test_config_defaults_and_save(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            custom_path = Path(tmp_dir) / "config.json"
            cfg = load_client_config(config_path=custom_path)
            self.assertEqual(cfg.get("language"), "en")
            self.assertFalse(cfg.get("auto_login"))
            self.assertEqual(cfg.get("saved_username"), "")
            self.assertEqual(cfg.get("saved_password"), "")

            save_client_config({
                "language": "en",
                "auto_login": True,
                "saved_username": "TestUser",
                "saved_password": "TestPassword123"
            }, config_path=custom_path)

            reloaded = load_client_config(config_path=custom_path)
            self.assertTrue(reloaded.get("auto_login"))
            self.assertEqual(reloaded.get("saved_username"), "TestUser")
            self.assertEqual(reloaded.get("saved_password"), "TestPassword123")

            clear_auto_login(config_path=custom_path)
            cleared = load_client_config(config_path=custom_path)
            self.assertFalse(cleared.get("auto_login"))
            self.assertEqual(cleared.get("saved_password"), "")
            self.assertEqual(cleared.get("saved_username"), "TestUser")


class TestFileUploadDatabase(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        db_path = os.path.join(self.tmp_dir.name, "test_file_upload.db")
        self.db = Database(db_path)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_save_and_retrieve_file_message(self):
        _, _, u1 = self.db.register_user("Sender", "password")
        _, _, u2 = self.db.register_user("Receiver", "password")

        fake_file_content = b"Hello, this is a binary document payload!" * 50
        fake_b64 = base64.b64encode(fake_file_content).decode("ascii")
        fake_name = "test_document.pdf"
        fake_size = len(fake_file_content)

        msg_id = self.db.save_message(
            sender_id=u1["user_id"],
            target_type="dm",
            target_id=u2["user_id"],
            content="Check out this file",
            file_data=fake_b64,
            file_name=fake_name,
            file_size=fake_size
        )
        self.assertIsNotNone(msg_id)

        msgs = self.db.get_messages("dm", u2["user_id"], peer_id=u1["user_id"])
        self.assertEqual(len(msgs), 1)
        m = msgs[0]
        self.assertEqual(m["content"], "Check out this file")
        self.assertEqual(m["file_data"], fake_b64)
        self.assertEqual(m["file_name"], fake_name)
        self.assertEqual(m["file_size"], fake_size)


class TestDirectLoginAndLargePayload(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        db_path = os.path.join(self.tmp_dir.name, "test_server_v040.db")
        self.db = Database(db_path)
        self.db.register_user("direct_user", "my_secret_pass")
        self.state = ServerState(self.db)
        self.tcp_server = TCPServer(self.state, "127.0.0.1", 29977)
        self.tcp_srv = await asyncio.start_server(
            self.tcp_server.handle_client,
            "127.0.0.1",
            29977,
            limit=64 * 1024 * 1024
        )

    async def asyncTearDown(self):
        self.tcp_srv.close()
        await self.tcp_srv.wait_closed()
        self.tmp_dir.cleanup()

    async def _read_json(self, reader):
        line = await asyncio.wait_for(reader.readline(), timeout=3.0)
        return decode_json_message(line.decode("utf-8").strip())

    async def test_direct_login_without_precheck_no_unbound_error(self):
        reader, writer = await asyncio.open_connection("127.0.0.1", 29977)
        req = {
            "type": "login",
            "username": "direct_user",
            "password": "my_secret_pass"
        }
        writer.write(encode_json_message(req).encode("utf-8") + b"\n")
        await writer.drain()

        resp = await self._read_json(reader)
        self.assertEqual(resp.get("type"), "login_resp")
        self.assertTrue(resp.get("success"))
        self.assertEqual(resp.get("username"), "direct_user")

        writer.close()
        await writer.wait_closed()

    async def test_wrong_password_does_not_crash_connection(self):
        reader, writer = await asyncio.open_connection("127.0.0.1", 29977)
        req = {
            "type": "login",
            "username": "direct_user",
            "password": "wrong_password"
        }
        writer.write(encode_json_message(req).encode("utf-8") + b"\n")
        await writer.drain()

        resp = await self._read_json(reader)
        self.assertEqual(resp.get("type"), "login_resp")
        self.assertFalse(resp.get("success"))

        req2 = {
            "type": "login",
            "username": "direct_user",
            "password": "my_secret_pass"
        }
        writer.write(encode_json_message(req2).encode("utf-8") + b"\n")
        await writer.drain()

        resp2 = await self._read_json(reader)
        self.assertEqual(resp2.get("type"), "login_resp")
        self.assertTrue(resp2.get("success"))

        writer.close()
        await writer.wait_closed()

    async def test_large_file_message_transfer(self):
        r1, w1 = await asyncio.open_connection("127.0.0.1", 29977)
        r2, w2 = await asyncio.open_connection("127.0.0.1", 29977)

        self.db.register_user("user_two", "pass2")

        w1.write(encode_json_message({"type": "login", "username": "direct_user", "password": "my_secret_pass"}).encode("utf-8") + b"\n")
        await w1.drain()
        u1_resp = await self._read_json(r1)
        u1_id = u1_resp["user_id"]

        w2.write(encode_json_message({"type": "login", "username": "user_two", "password": "pass2"}).encode("utf-8") + b"\n")
        await w2.drain()
        u2_resp = await self._read_json(r2)
        u2_id = u2_resp["user_id"]

        large_payload = "A" * (2 * 1024 * 1024)
        msg_req = {
            "type": "send_msg",
            "target_type": "dm",
            "target_id": u2_id,
            "content": "Sending large file",
            "file_data": large_payload,
            "file_name": "large_archive.zip",
            "file_size": 2 * 1024 * 1024
        }
        w1.write(encode_json_message(msg_req).encode("utf-8") + b"\n")
        await w1.drain()

        chat_msg = None
        for _ in range(5):
            incoming = await self._read_json(r2)
            if incoming.get("type") == "chat_msg":
                chat_msg = incoming
                break

        self.assertIsNotNone(chat_msg)
        self.assertEqual(chat_msg.get("file_name"), "large_archive.zip")
        self.assertEqual(chat_msg.get("file_data"), large_payload)
        self.assertEqual(chat_msg.get("file_size"), 2 * 1024 * 1024)

        w1.close()
        w2.close()
        await w1.wait_closed()
        await w2.wait_closed()


class TestSoundEffects(unittest.TestCase):
    def test_audio_chimes_exist(self):
        sounds_dir = Path(__file__).resolve().parents[1] / "vimcord" / "resources" / "sounds"
        expected_sounds = [
            "message.wav",
            "notification.wav",
            "join.wav",
            "leave.wav",
            "mute.wav",
            "unmute.wav",
            "deafen.wav",
            "undeafen.wav"
        ]
        for s in expected_sounds:
            sound_file = sounds_dir / s
            self.assertTrue(sound_file.exists(), f"Missing audio chime: {s}")
            self.assertGreater(sound_file.stat().st_size, 100, f"Sound file too small: {s}")


if __name__ == "__main__":
    unittest.main()
