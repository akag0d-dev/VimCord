"""
End-to-end integration test for VimCord TCP server and UDP voice/screen router.
"""

import asyncio
import os
import socket
import tempfile
import unittest
from vimcord.common.protocol import (
    encode_json_message,
    decode_json_message,
    pack_udp_audio,
    unpack_udp_audio,
    UDP_TYPE_REGISTER,
    UDP_TYPE_DM_AUDIO,
    UDP_TYPE_SCREEN_FRAME
)
from vimcord.server.db import Database
from vimcord.server.server_state import ServerState
from vimcord.server.tcp_server import TCPServer
from vimcord.server.udp_server import start_udp_server

TEST_TCP_PORT = 19988
TEST_UDP_PORT = 19989
TEST_HOST = "127.0.0.1"


class TestServerIntegration(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        db_path = os.path.join(self.tmp_dir.name, "integration_test.db")
        self.db = Database(db_path)
        self.state = ServerState(self.db)
        self.udp_transport = await start_udp_server(self.state, TEST_HOST, TEST_UDP_PORT)
        self.tcp_server = TCPServer(self.state, TEST_HOST, TEST_TCP_PORT)
        self.tcp_srv_obj = await asyncio.start_server(
            self.tcp_server.handle_client,
            TEST_HOST,
            TEST_TCP_PORT
        )

    async def asyncTearDown(self):
        self.udp_transport.close()
        self.tcp_srv_obj.close()
        await self.tcp_srv_obj.wait_closed()
        self.tmp_dir.cleanup()

    async def _read_json(self, reader: asyncio.StreamReader):
        line = await asyncio.wait_for(reader.readline(), timeout=3.0)
        return decode_json_message(line.decode("utf-8").strip())

    async def test_full_flow(self):
        # 1. Connect Client A (Alice)
        r_a, w_a = await asyncio.open_connection(TEST_HOST, TEST_TCP_PORT)
        w_a.write(encode_json_message({"type": "login", "username": "Alice"}))
        await w_a.drain()
        resp_a = await self._read_json(r_a)
        self.assertTrue(resp_a["success"])
        alice_id = resp_a["user_id"]
        self.assertEqual(resp_a["username"], "Alice")

        # 2. Connect Client B (Bob)
        r_b, w_b = await asyncio.open_connection(TEST_HOST, TEST_TCP_PORT)
        w_b.write(encode_json_message({"type": "login", "username": "Bob"}))
        await w_b.drain()
        resp_b = await self._read_json(r_b)
        self.assertTrue(resp_b["success"])
        bob_id = resp_b["user_id"]

        # Alice should receive user_presence for Bob
        pres_for_alice = await self._read_json(r_a)
        self.assertEqual(pres_for_alice["type"], "user_presence")
        self.assertEqual(pres_for_alice["user"]["username"], "Bob")

        # 3. Alice creates a room
        w_a.write(encode_json_message({"type": "create_room", "name": "Комната Алисы"}))
        await w_a.drain()
        
        # Both should receive room_created
        room_a = await self._read_json(r_a)
        room_b = await self._read_json(r_b)
        self.assertEqual(room_a["type"], "room_created")
        self.assertEqual(room_b["type"], "room_created")
        alice_room_id = room_a["room"]["room_id"]

        # 4. Alice creates a voice channel
        w_a.write(encode_json_message({
            "type": "create_channel",
            "room_id": alice_room_id,
            "name": "Голосовой 1",
            "channel_type": "voice"
        }))
        await w_a.drain()
        ch_a = await self._read_json(r_a)
        ch_b = await self._read_json(r_b)
        self.assertEqual(ch_a["type"], "channel_created")
        voice_ch_id = ch_a["channel"]["channel_id"]

        # 5. Alice joins voice channel
        w_a.write(encode_json_message({
            "type": "join_voice",
            "room_id": alice_room_id,
            "channel_id": voice_ch_id
        }))
        await w_a.drain()
        v_upd_a = await self._read_json(r_a)
        v_upd_b = await self._read_json(r_b)
        self.assertEqual(v_upd_a["type"], "voice_state_update")
        self.assertEqual(v_upd_a["action"], "join")

        # 6. Text message sending and history retrieval
        w_a.write(encode_json_message({
            "type": "send_msg",
            "target_type": "channel",
            "target_id": "ch-general",
            "content": "Привет, Боб!"
        }))
        await w_a.drain()
        msg_a = await self._read_json(r_a)
        msg_b = await self._read_json(r_b)
        self.assertEqual(msg_b["content"], "Привет, Боб!")
        self.assertEqual(msg_b["sender_name"], "Alice")

        # Request history from server
        w_b.write(encode_json_message({
            "type": "get_history",
            "target_type": "channel",
            "target_id": "ch-general"
        }))
        await w_b.drain()
        hist_b = await self._read_json(r_b)
        self.assertEqual(hist_b["type"], "history_resp")
        self.assertEqual(len(hist_b["messages"]), 1)
        self.assertEqual(hist_b["messages"][0]["content"], "Привет, Боб!")

        # 7. Direct 1-on-1 Call
        # Alice calls Bob
        w_a.write(encode_json_message({"type": "call_start", "target_user_id": bob_id}))
        await w_a.drain()

        ring_a = await self._read_json(r_a)
        self.assertEqual(ring_a["type"], "call_ringing")
        call_id = ring_a["call_id"]

        inc_b = await self._read_json(r_b)
        self.assertEqual(inc_b["type"], "incoming_call")
        self.assertEqual(inc_b["call_id"], call_id)
        self.assertEqual(inc_b["from_username"], "Alice")

        # Register UDP sockets for Alice and Bob
        udp_a = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp_a.bind(("", 0))
        udp_b = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp_b.bind(("", 0))
        udp_b.settimeout(2.0)

        # Send registration packets
        reg_a = pack_udp_audio(UDP_TYPE_REGISTER, 1, alice_id, "")
        reg_b = pack_udp_audio(UDP_TYPE_REGISTER, 1, bob_id, "")
        udp_a.sendto(reg_a, (TEST_HOST, TEST_UDP_PORT))
        udp_b.sendto(reg_b, (TEST_HOST, TEST_UDP_PORT))
        await asyncio.sleep(0.05)

        # Bob accepts call
        w_b.write(encode_json_message({"type": "call_accept", "call_id": call_id}))
        await w_b.drain()

        acc_a = await self._read_json(r_a)
        acc_b = await self._read_json(r_b)
        self.assertEqual(acc_a["type"], "call_accepted")
        self.assertEqual(acc_b["type"], "call_accepted")

        # Send test audio packet over UDP from Alice to Bob
        test_audio = b"\x12\x34\x56\x78" * 50
        audio_pkt = pack_udp_audio(UDP_TYPE_DM_AUDIO, 2, alice_id, call_id, test_audio)
        udp_a.sendto(audio_pkt, (TEST_HOST, TEST_UDP_PORT))

        # Bob reads incoming UDP packets until audio packet from Alice arrives
        payload = None
        for _ in range(3):
            data, _ = await asyncio.to_thread(udp_b.recvfrom, 65536)
            unpacked = unpack_udp_audio(data)
            if unpacked and unpacked[2] == alice_id:
                pkt_type, seq, sender_id, target_id, payload = unpacked
                break

        self.assertEqual(payload, test_audio)

        # Send test screen frame packet over UDP from Alice to Bob
        test_screen_frame = b"\xFF\xD8\xFF\xE0" + b"\x00" * 200 # Fake JPEG header
        screen_pkt = pack_udp_audio(UDP_TYPE_SCREEN_FRAME, 3, alice_id, call_id, test_screen_frame)
        udp_a.sendto(screen_pkt, (TEST_HOST, TEST_UDP_PORT))

        screen_payload = None
        for _ in range(3):
            data, _ = await asyncio.to_thread(udp_b.recvfrom, 65536)
            unpacked = unpack_udp_audio(data)
            if unpacked and unpacked[0] == UDP_TYPE_SCREEN_FRAME:
                pkt_type, seq, sender_id, target_id, screen_payload = unpacked
                break

        self.assertEqual(screen_payload, test_screen_frame)

        # Alice ends call
        w_a.write(encode_json_message({"type": "call_end", "call_id": call_id}))
        await w_a.drain()

        end_a = await self._read_json(r_a)
        end_b = await self._read_json(r_b)
        self.assertEqual(end_a["type"], "call_ended")
        self.assertEqual(end_b["type"], "call_ended")

        # Cleanup
        udp_a.close()
        udp_b.close()
        w_a.close()
        w_b.close()
        await w_a.wait_closed()
        await w_b.wait_closed()


if __name__ == "__main__":
    unittest.main()
