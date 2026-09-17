"""
Unit and integration tests for VimCord v0.3.0 features:
- Avatar image persistence & profile modal data
- Voice channel switching without ghost users
- Media state (mute/deafen) signaling
- VAD hangover and 0.005 threshold
- Avatar rendering helper
"""

import asyncio
import base64
import os
import tempfile
import unittest
import numpy as np

from vimcord.server.db import Database
from vimcord.server.server_state import ServerState
from vimcord.server.tcp_server import TCPServer
from vimcord.common.protocol import encode_json_message, decode_json_message
from vimcord.client.audio.audio_manager import AudioManager


class TestDatabaseV030(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        db_path = os.path.join(self.tmp_dir.name, "test_v030.db")
        self.db = Database(db_path)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_avatar_image_registration_and_update(self):
        # 1. Register user
        ok, msg, u = self.db.register_user("Alice", "pass123")
        self.assertTrue(ok)
        self.assertEqual(u["avatar_image"], "")

        # 2. Update profile with custom base64 avatar
        sample_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
        ok, msg = self.db.update_profile(
            u["user_id"],
            username="AliceUpdated",
            status_text="Coding VimCord",
            avatar_color="#57F287",
            avatar_image=sample_b64
        )
        self.assertTrue(ok)

        # 3. Retrieve user by ID
        fetched = self.db.get_user_by_id(u["user_id"])
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["username"], "AliceUpdated")
        self.assertEqual(fetched["status_text"], "Coding VimCord")
        self.assertEqual(fetched["avatar_color"], "#57F287")
        self.assertEqual(fetched["avatar_image"], sample_b64)

        # 4. Authenticate and verify avatar_image returned
        auth_ok, _, auth_u = self.db.authenticate_user("AliceUpdated", "pass123")
        self.assertTrue(auth_ok)
        self.assertEqual(auth_u["avatar_image"], sample_b64)

    def test_friends_query_includes_avatar_image(self):
        _, _, u1 = self.db.register_user("User1", "pass123")
        _, _, u2 = self.db.register_user("User2", "pass123")
        sample_b64 = "base64dataexample"
        self.db.update_profile(u2["user_id"], avatar_image=sample_b64)

        # Send and accept friend request
        self.db.send_friend_request(u1["user_id"], "User2")
        self.db.accept_friend_request(u2["user_id"], u1["user_id"])

        friends_of_u1 = self.db.get_friends(u1["user_id"])
        self.assertEqual(len(friends_of_u1), 1)
        self.assertEqual(friends_of_u1[0]["peer_id"], u2["user_id"])
        self.assertEqual(friends_of_u1[0]["avatar_image"], sample_b64)


class TestVoiceNoGhostingIntegration(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        db_path = os.path.join(self.tmp_dir.name, "test_ghost.db")
        self.db = Database(db_path)
        self.state = ServerState(self.db)
        self.tcp_server = TCPServer(self.state, "127.0.0.1", 29988)
        self.tcp_srv = await asyncio.start_server(
            self.tcp_server.handle_client,
            "127.0.0.1",
            29988
        )

    async def asyncTearDown(self):
        self.tcp_srv.close()
        await self.tcp_srv.wait_closed()
        self.tmp_dir.cleanup()

    async def _read_json(self, reader):
        line = await asyncio.wait_for(reader.readline(), timeout=3.0)
        return decode_json_message(line.decode("utf-8").strip())

    async def test_channel_switch_broadcasts_leave_and_join(self):
        # 1. Connect Client A
        r_a, w_a = await asyncio.open_connection("127.0.0.1", 29988)
        w_a.write(encode_json_message({"type": "login", "username": "GhostTester"}))
        await w_a.drain()
        login_resp = await self._read_json(r_a)
        self.assertTrue(login_resp["success"])
        default_room = login_resp["rooms"][0]
        room_id = default_room["room_id"]
        v_channels = [c for c in default_room["channels"] if c["channel_type"] == "voice"]
        self.assertGreaterEqual(len(v_channels), 2)
        vch_1 = v_channels[0]["channel_id"]
        vch_2 = v_channels[1]["channel_id"]

        # 2. Join Channel 1
        w_a.write(encode_json_message({"type": "join_voice", "room_id": room_id, "channel_id": vch_1}))
        await w_a.drain()
        msg1 = await self._read_json(r_a)
        self.assertEqual(msg1["type"], "voice_state_update")
        self.assertEqual(msg1["channel_id"], vch_1)
        self.assertEqual(msg1["action"], "join")

        # 3. Switch to Channel 2 -> must receive leave for ch_1 AND join for ch_2
        w_a.write(encode_json_message({"type": "join_voice", "room_id": room_id, "channel_id": vch_2}))
        await w_a.drain()

        ev_leave = await self._read_json(r_a)
        self.assertEqual(ev_leave["type"], "voice_state_update")
        self.assertEqual(ev_leave["channel_id"], vch_1)
        self.assertEqual(ev_leave["action"], "leave")

        ev_join = await self._read_json(r_a)
        self.assertEqual(ev_join["type"], "voice_state_update")
        self.assertEqual(ev_join["channel_id"], vch_2)
        self.assertEqual(ev_join["action"], "join")

        w_a.close()
        await w_a.wait_closed()

    async def test_user_media_state_broadcast(self):
        r_a, w_a = await asyncio.open_connection("127.0.0.1", 29988)
        w_a.write(encode_json_message({"type": "login", "username": "MuteTester"}))
        await w_a.drain()
        login_resp = await self._read_json(r_a)
        self.assertTrue(login_resp["success"])

        # Send user_media_state
        w_a.write(encode_json_message({"type": "user_media_state", "is_muted": True, "is_deafened": False}))
        await w_a.drain()
        ev = await self._read_json(r_a)
        self.assertEqual(ev["type"], "user_media_state")
        self.assertTrue(ev["is_muted"])
        self.assertFalse(ev["is_deafened"])

        w_a.close()
        await w_a.wait_closed()


class TestAudioHangover(unittest.TestCase):
    def test_vad_hangover_frames(self):
        mgr = AudioManager()
        mgr._is_running = True
        self.assertEqual(mgr.vad_threshold, 0.005)
        self.assertEqual(mgr.hangover_frames_max, 15)

        # Simulate speaking: silence first
        silence_frame = np.zeros(480, dtype=np.int16)
        mgr._input_callback(silence_frame, 480, None, None)
        self.assertFalse(mgr.is_speaking)
        self.assertEqual(mgr.hangover_counter, 0)

        # Loud frame (RMS > 0.005)
        loud_frame = np.full(480, 10000, dtype=np.int16)
        mgr._input_callback(loud_frame, 480, None, None)
        self.assertTrue(mgr.is_speaking)
        self.assertEqual(mgr.hangover_counter, 15)

        # 1 frame of silence -> should STILL be speaking due to hangover!
        mgr._input_callback(silence_frame, 480, None, None)
        self.assertTrue(mgr.is_speaking)
        self.assertEqual(mgr.hangover_counter, 14)

        # 14 more frames of silence
        for _ in range(14):
            mgr._input_callback(silence_frame, 480, None, None)

        # Now hangover counter reaches 0 -> is_speaking becomes False
        self.assertFalse(mgr.is_speaking)
        self.assertEqual(mgr.hangover_counter, 0)


if __name__ == "__main__":
    unittest.main()
