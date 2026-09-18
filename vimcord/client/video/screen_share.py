"""
Screen Sharing capture and streaming engine for VimCord.
Uses cross-platform mss screen capture and Pillow JPEG compression in a daemon thread.
No Qt dependency.
"""

import io
import logging
import threading
import time
from typing import Optional, Callable
import mss
from PIL import Image

from vimcord.client.config import load_config, save_config
from vimcord.client.signals import Signal
from vimcord.common.protocol import pack_udp_audio, UDP_TYPE_SCREEN_FRAME

logger = logging.getLogger("VimCord.ScreenShare")

RESOLUTION_PRESETS = {
    "480p": (854, 480),
    "720p": (1280, 720),
    "1080p": (1920, 1080)
}


class ScreenCapturer:
    def __init__(self, send_func: Optional[Callable[[bytes], None]] = None):
        self.send_func = send_func
        self.on_frame_ready: Optional[Callable[[str, str, bytes], None]] = None
        self.frame_captured = Signal(bytes)
        self.is_sharing: bool = False
        self.user_id: str = ""
        self.target_id: str = ""
        self.target_type: str = "channel"
        self._seq: int = 0
        self._thread: Optional[threading.Thread] = None

        # Load persisted settings from client config
        cfg = load_config()
        preset = cfg.get("stream_resolution", "720p")
        if preset not in RESOLUTION_PRESETS:
            preset = "720p"
        self.current_preset = preset
        self.fps = min(30, max(5, int(cfg.get("stream_fps", 15))))
        self.quality = int(cfg.get("stream_quality", 45))

        w, h = RESOLUTION_PRESETS.get(self.current_preset, (1280, 720))
        self.res_width = w
        self.res_height = h

    def set_stream_settings(self, resolution: str = "720p", fps: int = 15, quality: int = 45):
        """Sets resolution preset, FPS, and JPEG quality, and persists them to config."""
        if resolution in RESOLUTION_PRESETS:
            self.current_preset = resolution
            w, h = RESOLUTION_PRESETS[resolution]
            self.res_width = w
            self.res_height = h

        self.fps = max(5, min(30, fps))
        self.quality = max(20, min(85, quality))

        try:
            cfg = load_config()
            cfg["stream_resolution"] = self.current_preset
            cfg["stream_fps"] = self.fps
            cfg["stream_quality"] = self.quality
            save_config(cfg)
        except Exception as e:
            logger.debug(f"Failed to save screen settings: {e}")

        logger.info(f"Screen share settings updated: {self.current_preset} ({self.res_width}x{self.res_height}), {self.fps} FPS, quality {self.quality}")

    def start_sharing(self, user_id: str, target_id: str, target_type: str = "channel"):
        self.user_id = user_id
        self.target_id = target_id
        self.target_type = target_type
        self.is_sharing = True

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=0.5)

        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()
        logger.info(f"Screen sharing started: target {target_id} ({target_type}), {self.res_width}x{self.res_height} @ {self.fps} FPS")

    def stop_sharing(self):
        self.is_sharing = False
        self.target_id = ""
        logger.info("Screen sharing stopped")

    def _capture_loop(self):
        try:
            with mss.mss() as sct:
                monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
                while self.is_sharing:
                    t0 = time.time()
                    try:
                        sct_img = sct.grab(monitor)
                        img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
                        if img.size != (self.res_width, self.res_height):
                            img = img.resize((self.res_width, self.res_height), Image.Resampling.BILINEAR)
                        buf = io.BytesIO()
                        img.save(buf, format="JPEG", quality=self.quality)
                        jpeg_data = buf.getvalue()
                        if jpeg_data and self.is_sharing:
                            self._on_worker_frame(jpeg_data)
                    except Exception as e:
                        logger.debug(f"Screen capture frame error: {e}")

                    elapsed = time.time() - t0
                    interval = 1.0 / self.fps
                    sleep_time = interval - elapsed
                    if sleep_time > 0:
                        time.sleep(sleep_time)
        except Exception as e:
            logger.error(f"Error in screen capture loop: {e}")

    def _on_worker_frame(self, jpeg_data: bytes):
        if not self.is_sharing or not self.user_id or not self.target_id:
            return

        if self.on_frame_ready:
            self.on_frame_ready(self.target_type, self.target_id, jpeg_data)
        elif self.send_func and len(jpeg_data) <= 60000:
            self._seq = (self._seq + 1) % (2**32)
            pkt = pack_udp_audio(
                pkt_type=UDP_TYPE_SCREEN_FRAME,
                seq=self._seq,
                sender_id=self.user_id,
                target_id=self.target_id,
                payload=jpeg_data
            )
            self.send_func(pkt)

        self.frame_captured.emit(jpeg_data)

