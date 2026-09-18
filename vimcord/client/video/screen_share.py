"""
Screen Sharing capture and streaming engine for VimCord.
Uses off-main-thread PyQt6 screen capture in a background QThread worker
to completely eliminate UI lag and Windows mouse cursor flickering.
Persists resolution, FPS, and quality settings in client config.
"""

import logging
import time
from typing import Optional, Callable
from PyQt6.QtCore import QObject, QThread, pyqtSignal, QByteArray, QBuffer, QIODevice, Qt
from PyQt6.QtGui import QGuiApplication, QPixmap

from vimcord.client.config import load_config, save_config
from vimcord.common.protocol import pack_udp_audio, UDP_TYPE_SCREEN_FRAME

logger = logging.getLogger("VimCord.ScreenShare")

RESOLUTION_PRESETS = {
    "360p": (640, 360),
    "480p": (854, 480),
    "720p": (1280, 720),
    "1080p": (1920, 1080)
}


class ScreenCaptureWorker(QThread):
    frame_ready = pyqtSignal(bytes)

    def __init__(self, res_width: int, res_height: int, fps: int, quality: int, parent=None):
        super().__init__(parent)
        self.res_width = res_width
        self.res_height = res_height
        self.fps = fps
        self.quality = quality
        self.is_running = False

    def update_settings(self, width: int, height: int, fps: int, quality: int):
        self.res_width = width
        self.res_height = height
        self.fps = max(5, min(60, fps))
        self.quality = max(20, min(85, quality))

    def stop(self):
        self.is_running = False

    def run(self):
        self.is_running = True
        logger.info(f"Screen capture background worker started ({self.res_width}x{self.res_height} @ {self.fps} FPS, Q={self.quality})")

        while self.is_running:
            t0 = time.perf_counter()
            try:
                screen = QGuiApplication.primaryScreen()
                if screen:
                    pixmap = screen.grabWindow(0)
                    if not pixmap.isNull():
                        scaled = pixmap.scaled(
                            self.res_width, self.res_height,
                            Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.FastTransformation
                        )
                        byte_arr = QByteArray()
                        buffer = QBuffer(byte_arr)
                        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
                        scaled.save(buffer, "JPEG", self.quality)
                        jpeg_data = bytes(byte_arr.data())
                        if jpeg_data and self.is_running:
                            self.frame_ready.emit(jpeg_data)
            except Exception as e:
                logger.debug(f"Screen capture frame error: {e}")

            target_delay = 1.0 / self.fps
            elapsed = time.perf_counter() - t0
            sleep_time = target_delay - elapsed
            if sleep_time > 0.001:
                time.sleep(sleep_time)
            elif sleep_time < -0.05:
                time.sleep(0.005)

        logger.info("Screen capture background worker terminated")


class ScreenCapturer(QObject):
    frame_captured = pyqtSignal(bytes)

    def __init__(self, send_func: Optional[Callable[[bytes], None]] = None, parent=None):
        super().__init__(parent)
        self.send_func = send_func
        self.on_frame_ready: Optional[Callable[[str, str, bytes], None]] = None
        self.is_sharing: bool = False
        self.user_id: str = ""
        self.target_id: str = ""
        self.target_type: str = "channel"
        self._seq: int = 0
        self.worker: Optional[ScreenCaptureWorker] = None

        # Load persisted settings from client config
        cfg = load_config()
        self.current_preset = cfg.get("stream_resolution", "720p")
        self.fps = int(cfg.get("stream_fps", 15))
        self.quality = int(cfg.get("stream_quality", 45))

        w, h = RESOLUTION_PRESETS.get(self.current_preset, (1280, 720))
        self.res_width = w
        self.res_height = h

    def set_stream_settings(self, resolution: str = "720p", fps: int = 15, quality: int = 45):
        """Sets resolution preset, FPS, and JPEG quality, and persists them to config."""
        self.current_preset = resolution
        w, h = RESOLUTION_PRESETS.get(resolution, (1280, 720))
        self.res_width = w
        self.res_height = h
        self.fps = max(5, min(60, fps))
        self.quality = max(20, min(85, quality))

        if self.worker and self.worker.isRunning():
            self.worker.update_settings(self.res_width, self.res_height, self.fps, self.quality)

        try:
            cfg = load_config()
            cfg["stream_resolution"] = resolution
            cfg["stream_fps"] = self.fps
            cfg["stream_quality"] = self.quality
            save_config(cfg)
        except Exception as e:
            logger.debug(f"Failed to save screen settings: {e}")

        logger.info(f"Screen share settings updated: {resolution} ({w}x{h}), {self.fps} FPS, quality {self.quality}")

    def start_sharing(self, user_id: str, target_id: str, target_type: str = "channel"):
        self.user_id = user_id
        self.target_id = target_id
        self.target_type = target_type
        self.is_sharing = True

        if self.worker:
            self.worker.stop()
            self.worker.wait(300)

        self.worker = ScreenCaptureWorker(
            self.res_width, self.res_height, self.fps, self.quality, self
        )
        self.worker.frame_ready.connect(self._on_worker_frame)
        self.worker.start()
        logger.info(f"Screen sharing started for target: {target_id} ({target_type})")

    def stop_sharing(self):
        self.is_sharing = False
        if self.worker:
            self.worker.stop()
            self.worker.wait(300)
            self.worker = None
        self.target_id = ""
        logger.info("Screen sharing stopped")

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
