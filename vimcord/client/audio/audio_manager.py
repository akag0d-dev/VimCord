"""
Audio Manager using sounddevice for low-latency capture, VAD, and mixed playback.
"""

import collections
import logging
import sys
import threading
import time
from typing import Callable, Dict, List, Optional, Tuple
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
    generate_leave_sound,
    generate_message_sound,
    generate_notification_sound,
    generate_mute_sound,
    generate_unmute_sound,
    generate_deafen_sound,
    generate_undeafen_sound
)

logger = logging.getLogger("VimCord.AudioManager")


class RealtimeNoiseFilter:
    """
    Real-time audio DSP filter:
    1. 80Hz High-Pass Filter (cuts low-frequency mic rumble, desk bumps, AC hum)
    2. Dynamic noise floor tracking (estimates steady-state background hiss/fan noise)
    3. Spectral Subtraction / Soft Noise Gating with smooth exponential attack and release
    """
    def __init__(self, sample_rate: int = 48000, frame_size: int = 960):
        self.sample_rate = sample_rate
        self.frame_size = frame_size
        self.has_scipy = False
        try:
            from scipy.signal import butter
            self.b, self.a = butter(2, 80.0 / (sample_rate / 2.0), btype='highpass')
            self.zi = np.zeros(max(len(self.a), len(self.b)) - 1, dtype=np.float32)
            self.has_scipy = True
        except Exception:
            self.prev_x = 0.0
            self.prev_y = 0.0

        self.noise_profile = np.ones(frame_size // 2 + 1, dtype=np.float32) * 1e-4
        self.gain_envelope = 1.0
        self.alpha_noise = 0.05
        self.attack_coef = 0.4
        self.release_coef = 0.05

    def process(self, pcm_int16: np.ndarray, is_speaking: bool) -> np.ndarray:
        x = pcm_int16.astype(np.float32) / 32768.0

        # 1. High-pass rumble filter
        if self.has_scipy:
            from scipy.signal import lfilter
            x_filtered, self.zi = lfilter(self.b, self.a, x, zi=self.zi)
        else:
            dt = 1.0 / self.sample_rate
            rc = 1.0 / (2.0 * np.pi * 80.0)
            alpha = rc / (rc + dt)
            x_filtered = np.zeros_like(x)
            for i in range(len(x)):
                y = alpha * (self.prev_y + x[i] - self.prev_x)
                self.prev_x = x[i]
                self.prev_y = y
                x_filtered[i] = y

        # 2. FFT Spectral Gating
        spectrum = np.fft.rfft(x_filtered)
        mag = np.abs(spectrum)

        frame_energy = float(np.mean(mag))
        if not is_speaking or frame_energy < 0.003:
            self.noise_profile = (1.0 - self.alpha_noise) * self.noise_profile + self.alpha_noise * mag

        snr = mag / (self.noise_profile + 1e-6)
        spectral_gain = np.clip(1.0 - (1.5 / (snr + 0.1)), 0.08, 1.0)
        cleaned_spectrum = spectrum * spectral_gain
        cleaned_time = np.fft.irfft(cleaned_spectrum, n=len(x))

        # 3. Dynamic envelope gate (smooth hysteresis between speaking and silence)
        target_gain = 1.0 if is_speaking else 0.02
        if target_gain > self.gain_envelope:
            self.gain_envelope += self.attack_coef * (target_gain - self.gain_envelope)
        else:
            self.gain_envelope += self.release_coef * (target_gain - self.gain_envelope)

        output = cleaned_time * self.gain_envelope
        return np.clip(output * 32767.0, -32768.0, 32767.0).astype(np.int16)


class AudioManager:
    def __init__(self):
        self.input_device: Optional[int] = None
        self.output_device: Optional[int] = None
        
        self.is_muted: bool = False
        self.is_deafened: bool = False
        self.vad_threshold: float = 0.005
        self.hangover_frames_max: int = 15  # 300 ms hold-time to prevent word-ending cutoffs
        self.hangover_counter: int = 0
        self.is_speaking: bool = False
        self.output_volume: float = 1.0
        self.mic_volume: float = 1.0
        self.loopback_test: bool = False

        # Advanced Audio Features & DSP
        self.peer_volumes: Dict[str, float] = {}
        self.peer_muted: set = set()
        self.ptt_mode: bool = False
        self.ptt_active: bool = False
        self.noise_suppression: bool = True
        self._noise_filter = RealtimeNoiseFilter(SAMPLE_RATE, SAMPLES_PER_FRAME)
        self._recording_voice_msg: bool = False
        self._voice_msg_frames: List[bytes] = []
        self._voice_msg_start_time: float = 0.0

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

        self.stop_desktop_audio_capture()

    def start_desktop_audio_capture(self):
        """Captures system/desktop audio during screen sharing to transmit screen sound."""
        if getattr(self, "_desktop_stream", None) is not None or getattr(self, "_desktop_pyaudio_stream", None) is not None:
            return

        self._desktop_buffer = collections.deque(maxlen=15)

        # 1. Primary engine: Windows WASAPI Loopback via pyaudiowpatch (captures exact speaker/headphone sound)
        if sys.platform == "win32":
            try:
                import pyaudiowpatch as pyaudio
                p = pyaudio.PyAudio()
                wasapi_info = p.get_host_api_info_by_type(pyaudio.paWASAPI)
                default_speakers = p.get_device_info_by_index(wasapi_info["defaultOutputDevice"])
                
                loopback_dev = None
                if default_speakers.get("isLoopbackDevice"):
                    loopback_dev = default_speakers
                else:
                    for loopback in p.get_loopback_device_info_generator():
                        if default_speakers["name"] in loopback["name"]:
                            loopback_dev = loopback
                            break
                    if not loopback_dev:
                        loopback_dev = p.get_default_wasapi_loopback()

                if loopback_dev:
                    in_channels = int(loopback_dev["maxInputChannels"])
                    rate = int(loopback_dev["defaultSampleRate"])

                    def _wasapi_cb(in_data, frame_count, time_info, status):
                        try:
                            arr = np.frombuffer(in_data, dtype=np.int16)
                            if in_channels == 2:
                                mono = (arr[0::2].astype(np.int32) + arr[1::2].astype(np.int32)) // 2
                                mono_bytes = mono.astype(np.int16).tobytes()
                            else:
                                mono_bytes = in_data
                            if hasattr(self, "_desktop_buffer"):
                                self._desktop_buffer.append(mono_bytes)
                        except Exception:
                            pass
                        return (None, pyaudio.paContinue)

                    stream = p.open(
                        format=pyaudio.paInt16,
                        channels=in_channels,
                        rate=rate,
                        input=True,
                        input_device_index=loopback_dev["index"],
                        frames_per_buffer=SAMPLES_PER_FRAME,
                        stream_callback=_wasapi_cb
                    )
                    stream.start_stream()
                    self._desktop_pyaudio = p
                    self._desktop_pyaudio_stream = stream
                    logger.info(f"Started WASAPI loopback desktop audio capture on device: {loopback_dev['name']}")
                    return
            except Exception as e:
                logger.debug(f"pyaudiowpatch loopback failed, trying fallback: {e}")

        # 2. Fallback engine: sounddevice stereo mix
        try:
            stereo_dev = None
            devs = sd.query_devices()
            for idx, d in enumerate(devs):
                if d.get("max_input_channels", 0) > 0:
                    name_lower = d.get("name", "").lower()
                    if any(k in name_lower for k in ("стерео микшер", "stereo mix", "what u hear", "loopback", "wave out")):
                        stereo_dev = idx
                        break
            if stereo_dev is not None:
                def _desktop_cb(indata, frames, time_info, status):
                    raw = indata.tobytes()
                    if hasattr(self, "_desktop_buffer"):
                        self._desktop_buffer.append(raw)

                self._desktop_stream = sd.InputStream(
                    samplerate=SAMPLE_RATE,
                    channels=CHANNELS,
                    dtype="int16",
                    blocksize=SAMPLES_PER_FRAME,
                    device=stereo_dev,
                    callback=_desktop_cb
                )
                self._desktop_stream.start()
                logger.info(f"Started sounddevice desktop audio capture on device {stereo_dev}")
        except Exception as e:
            logger.debug(f"Desktop audio capture not available: {e}")

    def stop_desktop_audio_capture(self):
        if getattr(self, "_desktop_pyaudio_stream", None) is not None:
            try:
                self._desktop_pyaudio_stream.stop_stream()
                self._desktop_pyaudio_stream.close()
            except Exception:
                pass
            self._desktop_pyaudio_stream = None

        if getattr(self, "_desktop_pyaudio", None) is not None:
            try:
                self._desktop_pyaudio.terminate()
            except Exception:
                pass
            self._desktop_pyaudio = None

        if getattr(self, "_desktop_stream", None) is not None:
            try:
                self._desktop_stream.stop()
                self._desktop_stream.close()
            except Exception:
                pass
            self._desktop_stream = None

        if hasattr(self, "_desktop_buffer"):
            self._desktop_buffer.clear()

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

    def play_message_chime(self):
        self.play_sound_effect(generate_message_sound())

    def play_notification_chime(self):
        self.play_sound_effect(generate_notification_sound())

    def play_mute_chime(self, is_muted: bool):
        snd = generate_mute_sound() if is_muted else generate_unmute_sound()
        self.play_sound_effect(snd)

    def play_deafen_chime(self, is_deafened: bool):
        snd = generate_deafen_sound() if is_deafened else generate_undeafen_sound()
        self.play_sound_effect(snd)

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

    def set_peer_volume(self, user_id: str, volume: float):
        """Sets individual peer playback volume (0.0 to 2.0)."""
        self.peer_volumes[user_id] = max(0.0, min(2.0, volume))

    def get_peer_volume(self, user_id: str) -> float:
        return self.peer_volumes.get(user_id, 1.0)

    def set_peer_muted(self, user_id: str, muted: bool):
        """Mutes a peer locally without affecting others."""
        if muted:
            self.peer_muted.add(user_id)
        else:
            self.peer_muted.discard(user_id)

    def is_peer_muted(self, user_id: str) -> bool:
        return user_id in self.peer_muted

    def set_ptt_mode(self, enabled: bool):
        self.ptt_mode = enabled

    def set_ptt_active(self, active: bool):
        self.ptt_active = active

    def set_noise_suppression(self, enabled: bool):
        self.noise_suppression = enabled

    def start_recording_voice_msg(self):
        """Starts recording incoming microphone input for a voice message."""
        with self._lock:
            self._voice_msg_frames = []
            self._voice_msg_start_time = time.time()
            self._recording_voice_msg = True

    def stop_recording_voice_msg(self) -> Tuple[str, float]:
        """Stops recording, downsamples to 24kHz for lightweight fast transmission, and returns (base64_pcm, duration_seconds)."""
        import base64
        with self._lock:
            self._recording_voice_msg = False
            raw_pcm = b"".join(self._voice_msg_frames)
            duration = max(0.2, time.time() - self._voice_msg_start_time)
            self._voice_msg_frames = []
            if not raw_pcm:
                return "", 0.0
            arr = np.frombuffer(raw_pcm, dtype=np.int16)
            downsampled = arr[::2].tobytes()
            b64_str = base64.b64encode(downsampled).decode("ascii")
            return b64_str, round(duration, 1)

    def play_voice_msg(self, data_b64: str, duration: float = 0.0):
        """Plays a received base64-encoded voice message directly via sounddevice."""
        import base64
        try:
            raw_pcm = base64.b64decode(data_b64)
            if not raw_pcm:
                return
            audio_arr = np.frombuffer(raw_pcm, dtype=np.int16)
            if len(audio_arr) == 0:
                return
            rate = 24000
            if duration > 0 and (len(audio_arr) / duration) > 36000:
                rate = 48000
            try:
                sd.stop()
            except Exception:
                pass
            sd.play(audio_arr, samplerate=rate, device=self.output_device)
        except Exception as e:
            logger.error(f"Error playing voice message: {e}")

    def _input_callback(self, indata, frames, time_info, status):
        """Microphone capture callback."""
        if not self._is_running:
            return
        
        raw_bytes = indata.tobytes()
        if self.mic_volume != 1.0:
            raw_bytes = adjust_volume(raw_bytes, self.mic_volume)

        # Record into voice message if active
        if self._recording_voice_msg:
            with self._lock:
                self._voice_msg_frames.append(raw_bytes)

        rms = calculate_rms(raw_bytes)
        above_threshold = (rms >= self.vad_threshold)
        if above_threshold:
            self.hangover_counter = self.hangover_frames_max
        elif self.hangover_counter > 0:
            self.hangover_counter -= 1

        # Check mic voice status
        if self.is_muted:
            mic_speaking = False
        elif self.ptt_mode:
            mic_speaking = self.ptt_active
        else:
            mic_speaking = (above_threshold or self.hangover_counter > 0)

        self.is_speaking = mic_speaking

        # Real-time Noise Suppression DSP (80Hz rumble filter + spectral gating + hysteresis)
        if self.noise_suppression:
            arr = np.frombuffer(raw_bytes, dtype=np.int16)
            filtered_arr = self._noise_filter.process(arr, mic_speaking)
            processed_mic = filtered_arr.tobytes() if mic_speaking else b""
        elif mic_speaking:
            processed_mic = raw_bytes
        else:
            processed_mic = b""

        # Check desktop audio from screen sharing
        dt_chunk = b""
        has_desktop_audio = False
        if hasattr(self, "_desktop_buffer") and self._desktop_buffer:
            try:
                dt_chunk = self._desktop_buffer.popleft()
                if dt_chunk and len(dt_chunk) == len(raw_bytes):
                    dt_arr = np.frombuffer(dt_chunk, dtype=np.int16)
                    # Detect audible desktop sound (peak above background floor)
                    if np.max(np.abs(dt_arr)) > 250:
                        has_desktop_audio = True
            except Exception:
                pass

        # Mix mic and desktop audio
        if has_desktop_audio and processed_mic:
            final_payload = mix_audio_streams([processed_mic, dt_chunk])
            should_transmit = True
        elif has_desktop_audio:
            final_payload = dt_chunk
            should_transmit = True
        elif processed_mic:
            final_payload = processed_mic
            should_transmit = True
        else:
            final_payload = b""
            should_transmit = False

        if self.loopback_test and not self.is_muted:
            self.add_peer_audio("__loopback__", raw_bytes)

        if self.on_mic_frame:
            self.on_mic_frame(final_payload, should_transmit, rms)

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
                    raw_chunk = buf.popleft()
                    # Per-user local mute
                    if uid in self.peer_muted:
                        continue
                    # Per-user volume adjustment
                    peer_vol = self.peer_volumes.get(uid, 1.0)
                    if peer_vol != 1.0:
                        raw_chunk = adjust_volume(raw_chunk, peer_vol)
                    active_streams.append(raw_chunk)
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
