"""
Audio Manager using sounddevice for low-latency capture, VAD, and mixed playback.
"""

import collections
import logging
import threading
import time
from typing import Callable, Dict, List, Optional
import numpy as np
import sounddevice as sd

from vimcord.common.audio_codec import (
    calculate_rms,
    is_voice_active,
    adjust_volume,
    mix_audio_streams
)
from vimcord.common.protocol import (
    SAMPLE_RATE,
    CHANNELS,
    SAMPLES_PER_FRAME,
    BYTES_PER_SAMPLE
)
from vimcord.client.audio.ringtone import (
    generate_incoming_ringtone,
    generate_outgoing_ringtone,
    generate_join_sound,
    generate_leave_sound
)

logger = logging.getLogger("VimCord.AudioManager")


class AudioManager:
    def __init__(self):
        self.input_device: Optional[int] = None
        self.output_device: Optional[int] = None
        
        self.is_muted: bool = False
        self.is_deafened: bool = False
        self.vad_threshold: float = 0.02
        self.output_volume: float = 1.0
        self.mic_volume: float = 1.0
        self.loopback_test: bool = False

        # Ringtone playback state
        self._ringtone_type: Optional[str] = None
        self._ringtone_pos: int = 0
        self._ringtone_data: bytes = b""
        self._sound_effect_queue: collections.deque = collections.deque()

        # Incoming peer audio buffers: user_id -> deque of frames (bytes)
        self._peer_buffers: Dict[str, collections.deque] = {}
        self._peer_last_received: Dict[str, float] = {}
        self._lock = threading.Lock()

        # Callbacks
        self.on_mic_frame: Optional[Callable[[bytes, bool, float], None]] = None
        
        self._in_stream: Optional[sd.InputStream] = None
        self._out_stream: Optional[sd.OutputStream] = None
        self._is_running: bool = False

    @staticmethod
    def get_input_devices() -> List[Dict]:
        """Returns a list of all available audio input devices."""
        devices = []
        try:
            all_devs = sd.query_devices()
            for idx, dev in enumerate(all_devs):
                if dev.get("max_input_channels", 0) > 0:
                    devices.append({"index": idx, "name": dev["name"], "hostapi": dev.get("hostapi")})
        except Exception as e:
            logger.error(f"Error querying input devices: {e}")
        return devices

    @staticmethod
    def get_output_devices() -> List[Dict]:
        """Returns a list of all available audio output devices."""
        devices = []
        try:
            all_devs = sd.query_devices()
            for idx, dev in enumerate(all_devs):
                if dev.get("max_output_channels", 0) > 0:
                    devices.append({"index": idx, "name": dev["name"], "hostapi": dev.get("hostapi")})
        except Exception as e:
            logger.error(f"Error querying output devices: {e}")
        return devices

    def start(self):
        """Starts input and output audio streams."""
        if self._is_running:
            return
        self._is_running = True

        try:
            self._in_stream = sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype="int16",
                blocksize=SAMPLES_PER_FRAME,
                device=self.input_device,
                callback=self._input_callback
            )
            self._in_stream.start()
        except Exception as e:
            logger.error(f"Failed to start audio input stream: {e}")

        try:
            self._out_stream = sd.OutputStream(
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype="int16",
                blocksize=SAMPLES_PER_FRAME,
                device=self.output_device,
                callback=self._output_callback
            )
            self._out_stream.start()
        except Exception as e:
            logger.error(f"Failed to start audio output stream: {e}")

    def stop(self):
        """Stops audio streams and releases resources."""
        self._is_running = False
        if self._in_stream:
            try:
                self._in_stream.stop()
                self._in_stream.close()
            except Exception:
                pass
            self._in_stream = None

        if self._out_stream:
            try:
                self._out_stream.stop()
                self._out_stream.close()
            except Exception:
                pass
            self._out_stream = None

    def restart(self):
        self.stop()
        self.start()

    def set_input_device(self, index: Optional[int]):
        self.input_device = index
        if self._is_running:
            self.restart()

    def set_output_device(self, index: Optional[int]):
        self.output_device = index
        if self._is_running:
            self.restart()

    def add_peer_audio(self, user_id: str, audio_data: bytes):
        """Buffers incoming audio frame received from a peer."""
        with self._lock:
            if user_id not in self._peer_buffers:
                self._peer_buffers[user_id] = collections.deque(maxlen=15)
            self._peer_buffers[user_id].append(audio_data)
            self._peer_last_received[user_id] = time.time()

    def clear_peers(self):
        with self._lock:
            self._peer_buffers.clear()
            self._peer_last_received.clear()

    def play_sound_effect(self, sound_bytes: bytes):
        """Plays a one-time sound effect (e.g. join / leave chime)."""
        with self._lock:
            # Split into SAMPLES_PER_FRAME * 2 byte chunks
            chunk_size = SAMPLES_PER_FRAME * BYTES_PER_SAMPLE
            for i in range(0, len(sound_bytes), chunk_size):
                chunk = sound_bytes[i:i + chunk_size]
                if len(chunk) < chunk_size:
                    chunk = chunk.ljust(chunk_size, b"\x00")
                self._sound_effect_queue.append(chunk)

    def play_join_chime(self):
        self.play_sound_effect(generate_join_sound())

    def play_leave_chime(self):
        self.play_sound_effect(generate_leave_sound())

    def start_ringtone(self, ringtone_type: str = "incoming"):
        with self._lock:
            self._ringtone_type = ringtone_type
            self._ringtone_pos = 0
            if ringtone_type == "incoming":
                self._ringtone_data = generate_incoming_ringtone()
            else:
                self._ringtone_data = generate_outgoing_ringtone()

    def stop_ringtone(self):
        with self._lock:
            self._ringtone_type = None
            self._ringtone_pos = 0
            self._ringtone_data = b""

    def _input_callback(self, indata, frames, time_info, status):
        """Microphone capture callback."""
        if not self._is_running:
            return
        
        raw_bytes = indata.tobytes()
        if self.mic_volume != 1.0:
            raw_bytes = adjust_volume(raw_bytes, self.mic_volume)

        rms = calculate_rms(raw_bytes)
        is_speaking = False if self.is_muted else (rms >= self.vad_threshold)

        if self.loopback_test and not self.is_muted:
            self.add_peer_audio("__loopback__", raw_bytes)

        if self.on_mic_frame:
            payload = b"" if self.is_muted else raw_bytes
            self.on_mic_frame(payload, is_speaking, rms)

    def _output_callback(self, outdata, frames, time_info, status):
        """Speaker playback callback."""
        chunk_len_bytes = frames * BYTES_PER_SAMPLE * CHANNELS
        
        if self.is_deafened or not self._is_running:
            outdata.fill(0)
            return

        active_streams: List[bytes] = []
        now = time.time()

        with self._lock:
            # 1. Collect frames from peer voice channels / calls
            dead_peers = []
            for uid, buf in self._peer_buffers.items():
                if buf:
                    active_streams.append(buf.popleft())
                elif now - self._peer_last_received.get(uid, 0) > 3.0:
                    dead_peers.append(uid)
            
            for uid in dead_peers:
                del self._peer_buffers[uid]
                self._peer_last_received.pop(uid, None)

            # 2. Add one-shot sound effects
            if self._sound_effect_queue:
                active_streams.append(self._sound_effect_queue.popleft())

            # 3. Add looping ringtone if active
            if self._ringtone_data:
                ring_chunk = self._ringtone_data[self._ringtone_pos:self._ringtone_pos + chunk_len_bytes]
                if len(ring_chunk) < chunk_len_bytes:
                    # Loop ringtone
                    needed = chunk_len_bytes - len(ring_chunk)
                    ring_chunk += self._ringtone_data[:needed]
                    self._ringtone_pos = needed
                else:
                    self._ringtone_pos += chunk_len_bytes
                    if self._ringtone_pos >= len(self._ringtone_data):
                        self._ringtone_pos = 0
                active_streams.append(ring_chunk)

        if not active_streams:
            outdata.fill(0)
            return

        # Mix all streams
        mixed = mix_audio_streams(active_streams)
        if self.output_volume != 1.0:
            mixed = adjust_volume(mixed, self.output_volume)

        arr = np.frombuffer(mixed, dtype=np.int16)
        if len(arr) == frames:
            outdata[:] = arr.reshape(-1, 1)
        else:
            outdata.fill(0)
