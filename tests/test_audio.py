"""
Unit tests for audio utilities, VAD, RMS, and mixing.
"""

import unittest
import numpy as np
from vimcord.common.audio_codec import (
    calculate_rms,
    is_voice_active,
    adjust_volume,
    mix_audio_streams
)
from vimcord.common.protocol import SAMPLES_PER_FRAME

def generate_tone(freq: float, duration: float, volume: float = 0.5, sample_rate: int = 24000):
    t = np.linspace(0, duration, int(sample_rate * duration), False)
    tone = np.sin(freq * t * 2 * np.pi)
    return (tone * volume * 32767).astype(np.int16)

def generate_incoming_ringtone(duration: float = 0.5):
    return generate_tone(440.0, duration, volume=0.5).tobytes()

def generate_outgoing_ringtone(duration: float = 0.5):
    return generate_tone(400.0, duration, volume=0.5).tobytes()


class TestAudio(unittest.TestCase):
    def test_rms_silence(self):
        silence = np.zeros(SAMPLES_PER_FRAME, dtype=np.int16).tobytes()
        rms = calculate_rms(silence)
        self.assertEqual(rms, 0.0)
        self.assertFalse(is_voice_active(silence))

    def test_rms_sine_wave(self):
        # 1000 Hz sine wave
        sine = generate_tone(1000.0, 0.02, volume=0.5).tobytes()
        rms = calculate_rms(sine)
        self.assertGreater(rms, 0.1)
        self.assertTrue(is_voice_active(sine, threshold=0.05))

    def test_volume_adjustment(self):
        arr = np.array([1000, 2000, -2000], dtype=np.int16).tobytes()
        doubled = adjust_volume(arr, 2.0)
        doubled_arr = np.frombuffer(doubled, dtype=np.int16)
        np.testing.assert_array_equal(doubled_arr, np.array([2000, 4000, -4000], dtype=np.int16))

    def test_mix_audio_streams(self):
        s1 = np.full(SAMPLES_PER_FRAME, 10000, dtype=np.int16).tobytes()
        s2 = np.full(SAMPLES_PER_FRAME, 15000, dtype=np.int16).tobytes()
        mixed = mix_audio_streams([s1, s2])
        mixed_arr = np.frombuffer(mixed, dtype=np.int16)
        self.assertEqual(len(mixed_arr), SAMPLES_PER_FRAME)
        self.assertEqual(mixed_arr[0], 25000)

    def test_mix_clipping_protection(self):
        # Prevent 16-bit integer overflow
        s1 = np.full(SAMPLES_PER_FRAME, 25000, dtype=np.int16).tobytes()
        s2 = np.full(SAMPLES_PER_FRAME, 20000, dtype=np.int16).tobytes()
        mixed = mix_audio_streams([s1, s2])
        mixed_arr = np.frombuffer(mixed, dtype=np.int16)
        # Should saturate at 32767 rather than wrapping around into negative values
        self.assertEqual(mixed_arr[0], 32767)

    def test_procedural_ringtones(self):
        inc = generate_incoming_ringtone(0.5)
        self.assertGreater(len(inc), 0)
        outg = generate_outgoing_ringtone(0.5)
        self.assertGreater(len(outg), 0)


if __name__ == "__main__":
    unittest.main()
