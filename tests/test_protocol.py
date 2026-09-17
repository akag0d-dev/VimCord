"""
Unit tests for VimCord protocol serialization and deserialization.
"""

import unittest
from vimcord.common.protocol import (
    pack_udp_audio,
    unpack_udp_audio,
    encode_json_message,
    decode_json_message,
    UDP_TYPE_CHANNEL_AUDIO,
    UDP_TYPE_REGISTER,
    UDP_TYPE_DM_AUDIO
)


class TestProtocol(unittest.TestCase):
    def test_json_encode_decode(self):
        msg = {
            "type": "login",
            "username": "ТестовыйПользователь",
            "values": [1, 2, 3]
        }
        encoded = encode_json_message(msg)
        self.assertTrue(encoded.endswith(b"\n"))
        
        decoded = decode_json_message(encoded.decode("utf-8").strip())
        self.assertEqual(decoded["type"], "login")
        self.assertEqual(decoded["username"], "ТестовыйПользователь")
        self.assertEqual(decoded["values"], [1, 2, 3])

    def test_udp_audio_pack_unpack(self):
        payload = b"\x01\x02\x03\x04" * 100
        packet = pack_udp_audio(
            pkt_type=UDP_TYPE_CHANNEL_AUDIO,
            seq=12345,
            sender_id="u-alice123",
            target_id="vch-general",
            payload=payload
        )
        
        unpacked = unpack_udp_audio(packet)
        self.assertIsNotNone(unpacked)
        pkt_type, seq, sender_id, target_id, rec_payload = unpacked
        
        self.assertEqual(pkt_type, UDP_TYPE_CHANNEL_AUDIO)
        self.assertEqual(seq, 12345)
        self.assertEqual(sender_id, "u-alice123")
        self.assertEqual(target_id, "vch-general")
        self.assertEqual(rec_payload, payload)

    def test_udp_register_packet(self):
        packet = pack_udp_audio(
            pkt_type=UDP_TYPE_REGISTER,
            seq=1,
            sender_id="u-bob456",
            target_id=""
        )
        unpacked = unpack_udp_audio(packet)
        self.assertIsNotNone(unpacked)
        pkt_type, seq, sender_id, target_id, payload = unpacked
        self.assertEqual(pkt_type, UDP_TYPE_REGISTER)
        self.assertEqual(sender_id, "u-bob456")
        self.assertEqual(target_id, "")
        self.assertEqual(payload, b"")


if __name__ == "__main__":
    unittest.main()
