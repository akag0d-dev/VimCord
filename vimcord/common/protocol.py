"""
Network protocol definitions and packet serialization for VimCord.
"""

import json
import struct
import time
from typing import Optional, Tuple, Dict, Any

DEFAULT_TCP_PORT = 9988
DEFAULT_UDP_PORT = 9989

# Audio Stream Specs
SAMPLE_RATE = 24000
CHANNELS = 1
DTYPE = "int16"
BYTES_PER_SAMPLE = 2
FRAME_DURATION_MS = 20
SAMPLES_PER_FRAME = int(SAMPLE_RATE * FRAME_DURATION_MS / 1000)  # 480 samples
BYTES_PER_FRAME = SAMPLES_PER_FRAME * BYTES_PER_SAMPLE * CHANNELS  # 960 bytes

# UDP Packet Types
UDP_MAGIC = b"VC"
UDP_TYPE_REGISTER = 1      # Client announces UDP address to server
UDP_TYPE_CHANNEL_AUDIO = 2 # Audio for a room voice channel
UDP_TYPE_DM_AUDIO = 3      # Audio for 1-on-1 direct call
UDP_TYPE_PING = 4          # UDP Keep-alive / ping
UDP_TYPE_SPEAKING = 5      # VAD speaking state notification (lightweight)

# Header format:
# Magic: 2 bytes (VC)
# Type: 1 byte (B)
# Seq: 4 bytes (I)
# Sender ID len: 1 byte (B)
# Target ID len: 1 byte (B)
# Followed by sender_id_bytes, target_id_bytes, and audio payload.
UDP_HEADER_FORMAT = "!2sBIBB"
UDP_HEADER_SIZE = struct.calcsize(UDP_HEADER_FORMAT)  # 2 + 1 + 4 + 1 + 1 = 9 bytes


def pack_udp_audio(
    pkt_type: int,
    seq: int,
    sender_id: str,
    target_id: str,
    payload: bytes = b""
) -> bytes:
    """Serializes an audio or signaling packet for UDP transmission."""
    sender_bytes = sender_id.encode("utf-8")[:255]
    target_bytes = target_id.encode("utf-8")[:255]
    
    header = struct.pack(
        UDP_HEADER_FORMAT,
        UDP_MAGIC,
        pkt_type,
        seq % (2**32),
        len(sender_bytes),
        len(target_bytes)
    )
    return header + sender_bytes + target_bytes + payload


def unpack_udp_audio(data: bytes) -> Optional[Tuple[int, int, str, str, bytes]]:
    """
    Unpacks a UDP packet.
    Returns: (pkt_type, seq, sender_id, target_id, payload) or None if invalid.
    """
    if len(data) < UDP_HEADER_SIZE:
        return None
    
    magic, pkt_type, seq, s_len, t_len = struct.unpack_from(UDP_HEADER_FORMAT, data, 0)
    if magic != UDP_MAGIC:
        return None
    
    offset = UDP_HEADER_SIZE
    if len(data) < offset + s_len + t_len:
        return None
    
    sender_id = data[offset:offset + s_len].decode("utf-8", errors="ignore")
    offset += s_len
    target_id = data[offset:offset + t_len].decode("utf-8", errors="ignore")
    offset += t_len
    payload = data[offset:]
    
    return pkt_type, seq, sender_id, target_id, payload


def encode_json_message(msg: Dict[str, Any]) -> bytes:
    """Encodes a dictionary as newline-delimited JSON bytes."""
    return (json.dumps(msg, ensure_ascii=False) + "\n").encode("utf-8")


def decode_json_message(line: str) -> Optional[Dict[str, Any]]:
    """Decodes a single JSON line into a dict."""
    try:
        return json.loads(line)
    except Exception:
        return None
