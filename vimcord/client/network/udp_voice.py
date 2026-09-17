"""
UDP Voice Client for low-latency audio transmission and reception.
"""

import logging
import socket
import threading
import time
from typing import Optional
from PyQt6.QtCore import QObject, pyqtSignal

from vimcord.common.protocol import (
    pack_udp_audio,
    unpack_udp_audio,
    UDP_TYPE_REGISTER,
    UDP_TYPE_CHANNEL_AUDIO,
    UDP_TYPE_DM_AUDIO,
    UDP_TYPE_PING,
    UDP_TYPE_SPEAKING,
    UDP_TYPE_SCREEN_FRAME,
    UDP_TYPE_SCREEN_CHUNK,
    pack_screen_chunk,
    unpack_screen_chunk
)
from vimcord.client.audio.audio_manager import AudioManager

logger = logging.getLogger("VimCord.UDPVoice")


class UDPVoiceSignals(QObject):
    peer_speaking = pyqtSignal(str, bool)       # user_id, is_speaking
    screen_frame_received = pyqtSignal(str, bytes)  # sender_id, jpeg_bytes


class UDPVoiceClient:
    def __init__(self, audio_manager: AudioManager):
        self.audio_manager = audio_manager
        self.signals = UDPVoiceSignals()
        
        self.user_id: Optional[str] = None
        self.server_host: str = "127.0.0.1"
        self.server_udp_port: int = 9989

        # Target contexts
        self.current_channel_id: Optional[str] = None
        self.active_call_id: Optional[str] = None

        self.sock: Optional[socket.socket] = None
        self._is_running: bool = False
        self._rx_thread: Optional[threading.Thread] = None
        self._ping_thread: Optional[threading.Thread] = None
        self._seq: int = 0
        
        # Track active speakers for decay
        self._speaker_last_seen = {}
        self._speaker_decay_thread: Optional[threading.Thread] = None

        # Screen share frame fragmentation & assembly
        self._screen_frame_id: int = 0
        self._screen_reassembler: dict = {}

        # Bind audio manager's mic capture to our send_mic_frame
        self.audio_manager.on_mic_frame = self._on_mic_frame

    def start(self, user_id: str, server_host: str, server_udp_port: int):
        """Initializes the UDP socket and starts network threads."""
        self.user_id = user_id
        self.server_host = server_host
        self.server_udp_port = server_udp_port

        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            # Bind to all interfaces with an OS-assigned ephemeral port
            self.sock.bind(("", 0))
            self._is_running = True

            # Register with server
            self.register()

            self._rx_thread = threading.Thread(target=self._receive_loop, daemon=True)
            self._rx_thread.start()

            self._ping_thread = threading.Thread(target=self._ping_loop, daemon=True)
            self._ping_thread.start()

            self._speaker_decay_thread = threading.Thread(target=self._decay_loop, daemon=True)
            self._speaker_decay_thread.start()

            logger.info(f"UDP Voice Client started on port {self.sock.getsockname()[1]}")
        except Exception as e:
            logger.error(f"Failed to start UDP voice client: {e}")

    def stop(self):
        """Stops the UDP voice client and closes socket."""
        self._is_running = False
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None
        self.current_channel_id = None
        self.active_call_id = None

    def register(self):
        """Sends UDP registration packet so server learns our IP:port."""
        if not self.sock or not self.user_id:
            return
        pkt = pack_udp_audio(
            pkt_type=UDP_TYPE_REGISTER,
            seq=self._next_seq(),
            sender_id=self.user_id,
            target_id=""
        )
        self._send_raw(pkt)

    def _next_seq(self) -> int:
        self._seq = (self._seq + 1) % (2**32)
        return self._seq

    def _send_raw(self, data: bytes):
        if not self.sock or not self._is_running:
            return
        try:
            self.sock.sendto(data, (self.server_host, self.server_udp_port))
        except Exception as e:
            logger.debug(f"UDP sendto error: {e}")

    def _on_mic_frame(self, audio_data: bytes, is_speaking: bool, rms: float):
        """Callback from AudioManager whenever 20ms microphone audio is captured."""
        if not self._is_running or not self.user_id:
            return

        # Check if we are in a voice channel or active 1-on-1 call
        target_id = None
        pkt_type = None

        if self.active_call_id:
            target_id = self.active_call_id
            pkt_type = UDP_TYPE_DM_AUDIO
        elif self.current_channel_id:
            target_id = self.current_channel_id
            pkt_type = UDP_TYPE_CHANNEL_AUDIO

        if not target_id:
            return

        # If speaking, send audio frame. If silence, send speaking=False packet once
        if is_speaking and audio_data:
            pkt = pack_udp_audio(
                pkt_type=pkt_type,
                seq=self._next_seq(),
                sender_id=self.user_id,
                target_id=target_id,
                payload=audio_data
            )
            self._send_raw(pkt)
            # Emit local speaking indicator
            self.signals.peer_speaking.emit(self.user_id, True)
        else:
            self.signals.peer_speaking.emit(self.user_id, False)

    def send_screen_packet(self, data: bytes):
        self._send_raw(data)

    def send_screen_frame_chunks(self, target_id: str, jpeg_data: bytes):
        """Slices JPEG data into MTU-safe 1200-byte UDP datagram chunks and transmits them."""
        if not self._is_running or not self.sock or not self.user_id:
            return
        chunk_size = 1200
        total_len = len(jpeg_data)
        total_chunks = (total_len + chunk_size - 1) // chunk_size
        if total_chunks == 0:
            return

        self._screen_frame_id = (self._screen_frame_id + 1) % (2**32)
        fid = self._screen_frame_id

        for idx in range(total_chunks):
            start = idx * chunk_size
            end = min(start + chunk_size, total_len)
            chunk = jpeg_data[start:end]
            pkt = pack_screen_chunk(
                seq=self._next_seq(),
                sender_id=self.user_id,
                target_id=target_id,
                frame_id=fid,
                chunk_idx=idx,
                total_chunks=total_chunks,
                chunk_data=chunk
            )
            self._send_raw(pkt)

    def _receive_loop(self):
        """Receives incoming audio and screen packets from server and buffers them."""
        while self._is_running and self.sock:
            try:
                data, addr = self.sock.recvfrom(65536)
                if not data:
                    continue

                packet = unpack_udp_audio(data)
                if not packet:
                    continue

                pkt_type, seq, sender_id, target_id, payload = packet

                if pkt_type in (UDP_TYPE_CHANNEL_AUDIO, UDP_TYPE_DM_AUDIO):
                    if payload and sender_id != self.user_id:
                        self.audio_manager.add_peer_audio(sender_id, payload)
                        self._speaker_last_seen[sender_id] = time.time()
                        self.signals.peer_speaking.emit(sender_id, True)

                elif pkt_type == UDP_TYPE_SCREEN_FRAME:
                    if payload and sender_id != self.user_id:
                        self.signals.screen_frame_received.emit(sender_id, payload)

                elif pkt_type == UDP_TYPE_SCREEN_CHUNK:
                    if payload and sender_id != self.user_id:
                        unpacked = unpack_screen_chunk(payload)
                        if unpacked:
                            frame_id, chunk_idx, total_chunks, chunk_data = unpacked
                            key = (sender_id, frame_id)
                            now = time.time()
                            if key not in self._screen_reassembler:
                                # Clean up aged incomplete frames (> 2.0s)
                                stale = [k for k, v in self._screen_reassembler.items() if now - v["timestamp"] > 2.0]
                                for k in stale:
                                    self._screen_reassembler.pop(k, None)
                                self._screen_reassembler[key] = {
                                    "total": total_chunks,
                                    "chunks": {},
                                    "timestamp": now
                                }

                            entry = self._screen_reassembler[key]
                            entry["chunks"][chunk_idx] = chunk_data
                            if len(entry["chunks"]) == entry["total"]:
                                full_jpeg = b"".join(entry["chunks"][i] for i in range(entry["total"]))
                                self._screen_reassembler.pop(key, None)
                                self.signals.screen_frame_received.emit(sender_id, full_jpeg)

            except Exception as e:
                if self._is_running:
                    logger.debug(f"UDP recv error: {e}")
                    time.sleep(0.01)
                    continue
                break

    def _ping_loop(self):
        """Sends periodic UDP ping to keep NAT/firewall mapping open."""
        while self._is_running:
            time.sleep(3.0)
            if self.user_id and self.sock:
                pkt = pack_udp_audio(
                    pkt_type=UDP_TYPE_PING,
                    seq=self._next_seq(),
                    sender_id=self.user_id,
                    target_id=""
                )
                self._send_raw(pkt)

    def _decay_loop(self):
        """Decays speaking indicators if no audio packet received for 0.4s."""
        while self._is_running:
            time.sleep(0.15)
            now = time.time()
            for uid, last_t in list(self._speaker_last_seen.items()):
                if now - last_t > 0.4:
                    self.signals.peer_speaking.emit(uid, False)
                    self._speaker_last_seen.pop(uid, None)
