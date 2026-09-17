"""
Audio utilities: RMS computation, Voice Activity Detection (VAD), mixing, and volume adjustment.
"""

import math
import zlib
from typing import List, Optional
import numpy as np
from vimcord.common.protocol import SAMPLES_PER_FRAME, DTYPE


def calculate_rms(audio_data: bytes) -> float:
    """
    Computes RMS (Root Mean Square) volume level for 16-bit PCM mono audio.
    Returns a normalized value between 0.0 and 1.0.
    """
    if not audio_data:
        return 0.0
    
    samples = np.frombuffer(audio_data, dtype=np.int16)
    if len(samples) == 0:
        return 0.0
    
    # Calculate root mean square of samples
    rms = np.sqrt(np.mean(samples.astype(np.float32) ** 2))
    # Normalize with 32768 (max amplitude for int16)
    normalized = min(1.0, float(rms / 32768.0))
    return normalized


def is_voice_active(audio_data: bytes, threshold: float = 0.015) -> bool:
    """
    Determines if voice activity is present above a specified RMS threshold.
    """
    rms = calculate_rms(audio_data)
    return rms >= threshold


def adjust_volume(audio_data: bytes, volume_factor: float) -> bytes:
    """
    Adjusts the volume of 16-bit PCM audio by volume_factor (0.0 to 2.0).
    """
    if volume_factor == 1.0 or not audio_data:
        return audio_data
    
    samples = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32)
    samples = samples * volume_factor
    clipped = np.clip(samples, -32768, 32767).astype(np.int16)
    return clipped.tobytes()


def mix_audio_streams(streams: List[bytes]) -> bytes:
    """
    Mixes multiple 16-bit PCM mono audio chunks of equal length.
    Uses saturation clipping (-32768 to 32767) to prevent overflow distortion.
    """
    if not streams:
        return b"\x00" * (SAMPLES_PER_FRAME * 2)
    
    if len(streams) == 1:
        return streams[0]
    
    arrays = []
    target_len = SAMPLES_PER_FRAME
    for s in streams:
        arr = np.frombuffer(s, dtype=np.int16)
        if len(arr) < target_len:
            arr = np.pad(arr, (0, target_len - len(arr)))
        elif len(arr) > target_len:
            arr = arr[:target_len]
        arrays.append(arr.astype(np.float32))
    
    # Sum up all audio signals
    mixed = np.sum(arrays, axis=0)
    # Clip to prevent int16 overflow
    clipped = np.clip(mixed, -32768, 32767).astype(np.int16)
    return clipped.tobytes()


def compress_audio(audio_data: bytes) -> bytes:
    """Fast zlib compression for audio payload."""
    return zlib.compress(audio_data, level=1)


def decompress_audio(compressed_data: bytes) -> bytes:
    """Decompresses zlib-compressed audio payload."""
    try:
        return zlib.decompress(compressed_data)
    except Exception:
        return compressed_data
