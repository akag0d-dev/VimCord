"""
Procedural sound generator for ringtones and UI chimes without external media files.
"""

import numpy as np
from vimcord.common.protocol import SAMPLE_RATE


def generate_tone(frequency: float, duration_s: float, sample_rate: int = SAMPLE_RATE, volume: float = 0.3) -> np.ndarray:
    """Generates a pure sine wave with smooth attack/decay envelope."""
    t = np.linspace(0, duration_s, int(sample_rate * duration_s), endpoint=False)
    wave = np.sin(2 * np.pi * frequency * t)
    
    # Apply cosine fade-in and fade-out to prevent audio clicks
    fade_len = min(int(sample_rate * 0.01), len(wave) // 2)
    if fade_len > 0:
        fade_in = 0.5 * (1 - np.cos(np.linspace(0, np.pi, fade_len)))
        fade_out = 0.5 * (1 + np.cos(np.linspace(0, np.pi, fade_len)))
        wave[:fade_len] *= fade_in
        wave[-fade_len:] *= fade_out
        
    scaled = wave * (32767 * volume)
    return np.clip(scaled, -32768, 32767).astype(np.int16)


def generate_incoming_ringtone(duration_s: float = 1.6, sample_rate: int = SAMPLE_RATE) -> bytes:
    """Generates a melodic 3-note chime ringtone loop."""
    # Frequencies: C5 (523Hz), E5 (659Hz), G5 (784Hz)
    note_dur = 0.18
    c5 = generate_tone(523.25, note_dur, sample_rate, volume=0.25)
    e5 = generate_tone(659.25, note_dur, sample_rate, volume=0.25)
    g5 = generate_tone(783.99, note_dur, sample_rate, volume=0.25)
    pause_len = int(sample_rate * (duration_s - 3 * note_dur))
    pause = np.zeros(max(0, pause_len), dtype=np.int16)
    ringtone = np.concatenate([c5, e5, g5, pause])
    return ringtone.tobytes()


def generate_outgoing_ringtone(duration_s: float = 2.0, sample_rate: int = SAMPLE_RATE) -> bytes:
    """Generates an outgoing dial tone ring-back pattern (440Hz + 480Hz)."""
    tone_dur = 0.8
    t = np.linspace(0, tone_dur, int(sample_rate * tone_dur), endpoint=False)
    wave = 0.5 * np.sin(2 * np.pi * 440 * t) + 0.5 * np.sin(2 * np.pi * 480 * t)
    fade_len = int(sample_rate * 0.02)
    fade_in = 0.5 * (1 - np.cos(np.linspace(0, np.pi, fade_len)))
    fade_out = 0.5 * (1 + np.cos(np.linspace(0, np.pi, fade_len)))
    wave[:fade_len] *= fade_in
    wave[-fade_len:] *= fade_out
    tone = np.clip(wave * (32767 * 0.2), -32768, 32767).astype(np.int16)
    
    pause_len = int(sample_rate * (duration_s - tone_dur))
    pause = np.zeros(max(0, pause_len), dtype=np.int16)
    return np.concatenate([tone, pause]).tobytes()


def generate_join_sound(sample_rate: int = SAMPLE_RATE) -> bytes:
    """Rising two-tone chime when joining a voice channel."""
    t1 = generate_tone(440.0, 0.08, sample_rate, volume=0.2)
    t2 = generate_tone(880.0, 0.12, sample_rate, volume=0.25)
    return np.concatenate([t1, t2]).tobytes()


def generate_leave_sound(sample_rate: int = SAMPLE_RATE) -> bytes:
    """Falling two-tone chime when leaving a voice channel."""
    t1 = generate_tone(660.0, 0.08, sample_rate, volume=0.2)
    t2 = generate_tone(330.0, 0.12, sample_rate, volume=0.2)
    return np.concatenate([t1, t2]).tobytes()


def generate_message_sound(sample_rate: int = SAMPLE_RATE) -> bytes:
    """Soft warm harmonic bubble pop when receiving a chat message."""
    dur = 0.16
    t = np.linspace(0, dur, int(sample_rate * dur), endpoint=False)
    # Fundamental 659.25Hz (E5) + 987.77Hz (B5) with exponential decay
    env = np.exp(-18 * t)
    wave = 0.6 * np.sin(2 * np.pi * 659.25 * t) + 0.4 * np.sin(2 * np.pi * 987.77 * t)
    # Anti-click fade-in
    fade_len = int(sample_rate * 0.005)
    wave[:fade_len] *= np.linspace(0, 1, fade_len)
    scaled = wave * env * (32767 * 0.28)
    return np.clip(scaled, -32768, 32767).astype(np.int16).tobytes()


def generate_notification_sound(sample_rate: int = SAMPLE_RATE) -> bytes:
    """Melodic two-note chime for toast notifications (A5 -> C#6)."""
    t1 = generate_tone(880.0, 0.08, sample_rate, volume=0.22)
    t2 = generate_tone(1108.73, 0.15, sample_rate, volume=0.26)
    return np.concatenate([t1, t2]).tobytes()


def generate_mute_sound(sample_rate: int = SAMPLE_RATE) -> bytes:
    """Subtle downward click when muting."""
    dur = 0.05
    t = np.linspace(0, dur, int(sample_rate * dur), endpoint=False)
    freq = np.linspace(420.0, 210.0, len(t))
    env = np.exp(-25 * t)
    wave = np.sin(2 * np.pi * freq * t) * env * (32767 * 0.22)
    return np.clip(wave, -32768, 32767).astype(np.int16).tobytes()


def generate_unmute_sound(sample_rate: int = SAMPLE_RATE) -> bytes:
    """Crisp upward blip when unmuting."""
    dur = 0.05
    t = np.linspace(0, dur, int(sample_rate * dur), endpoint=False)
    freq = np.linspace(260.0, 560.0, len(t))
    env = np.exp(-20 * t)
    wave = np.sin(2 * np.pi * freq * t) * env * (32767 * 0.24)
    return np.clip(wave, -32768, 32767).astype(np.int16).tobytes()


def generate_deafen_sound(sample_rate: int = SAMPLE_RATE) -> bytes:
    """Low dampened tone when deafening."""
    dur = 0.07
    t = np.linspace(0, dur, int(sample_rate * dur), endpoint=False)
    env = np.exp(-16 * t)
    wave = np.sin(2 * np.pi * 200.0 * t) * env * (32767 * 0.22)
    return np.clip(wave, -32768, 32767).astype(np.int16).tobytes()


def generate_undeafen_sound(sample_rate: int = SAMPLE_RATE) -> bytes:
    """Bright upward chime when undeafening."""
    t1 = generate_tone(350.0, 0.04, sample_rate, volume=0.2)
    t2 = generate_tone(600.0, 0.08, sample_rate, volume=0.25)
    return np.concatenate([t1, t2]).tobytes()

