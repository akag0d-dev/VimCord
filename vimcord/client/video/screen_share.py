"""
Screen Sharing capture and streaming engine for VimCord.
Uses non-blocking main-thread window grab with offloaded background JPEG compression
in a QThread worker to completely eliminate UI lag, cross-thread pixmap crashes,
and Windows mouse cursor flickering.
Persists resolution, FPS, and quality settings in client config.
"""

import logging
import queue
import time
from typing import Optional, Callable
from PyQt6.QtCore import QObject, QThread, pyqtSignal, QByteArray, QBuffer, QIODevice, Qt, QTimer
from PyQt6.QtGui import QGuiApplication, QImage, QPixmap

from vimcord.client.config import load_config, save_config
from vimcord.common.protocol import pack_udp_audio, UDP_TYPE_SCREEN_FRAME

logger = logging.getLogger("VimCord.ScreenShare")

RESOLUTION_PRESETS = {
    "480p": (854, 480),
    "720p": (1280, 720),
    "1080p": (1920, 1080)
}


class ScreenCompressWorker(QThread):
    """
    Background worker that receives raw QImage frames, scales them,
    and encodes them into JPEG bytes off the GUI thread.
    """
    frame_ready = pyqtSignal(bytes)

    def __init__(self, res_width: int, res_height: int, quality: int, parent=None):
        super().__init__(parent)
        self.res_width = res_width
        self.res_height = res_height
        self.quality = quality
        self.is_running = False
        self._queue: queue.Queue = queue.Queue(maxsize=1)

    def update_settings(self, width: int, height: int, quality: int):
        self.res_width = width
        self.res_height = height
        self.quality = max(20, min(85, quality))

    def submit_frame(self, img: QImage):
        if not self.is_running:
            return
        # Discard older frame if worker is busy to keep latency ultra-low
        try:
            if self._queue.full():
                try:
                    self._queue.get_nowait()
                except queue.Empty:
                    pass
            self._queue.put_nowait(img)
        except Exception:
            pass

    def stop(self):
        self.is_running = False
        try:
            self._queue.put_nowait(None)
        except Exception:
            pass

    def run(self):
        self.is_running = True
        logger.info(f"Screen compress worker started ({self.res_width}x{self.res_height}, Q={self.quality})")

        while self.is_running:
            try:
                img = self._queue.get(timeout=0.2)
            except queue.Empty:
                continue

            if img is None or not self.is_running:
                break

            try:
                scaled = img.scaled(
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
                logger.debug(f"Screen compression error: {e}")

        logger.info("Screen compress worker terminated")


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
        self.worker: Optional[ScreenCompressWorker] = None

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_timer_tick)

        # Load persisted settings from client config
        cfg = load_config()
        preset = cfg.get("stream_resolution", "720p")
        if preset not in RESOLUTION_PRESETS:
            preset = "720p"
        self.current_preset = preset
        self.fps = min(30, max(5, int(cfg.get("stream_fps", 30))))
        self.quality = int(cfg.get("stream_quality", 45))

        w, h = RESOLUTION_PRESETS.get(self.current_preset, (1280, 720))
        self.res_width = w
        self.res_height = h

    def set_stream_settings(self, resolution: str = "720p", fps: int = 30, quality: int = 45):
        """Sets resolution preset, FPS, and JPEG quality, and persists them to config."""
        if resolution in RESOLUTION_PRESETS:
            self.current_preset = resolution
            w, h = RESOLUTION_PRESETS[resolution]
            self.res_width = w
            self.res_height = h

        self.fps = max(5, min(30, fps))
        self.quality = max(20, min(85, quality))

        if self._timer.isActive():
            self._timer.setInterval(max(10, int(1000 / self.fps)))

        if self.worker and self.worker.isRunning():
            self.worker.update_settings(self.res_width, self.res_height, self.quality)

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

        if self.worker:
            self.worker.stop()
            self.worker.wait(300)

        self.worker = ScreenCompressWorker(self.res_width, self.res_height, self.quality, self)
        self.worker.frame_ready.connect(self._on_worker_frame)
        self.worker.start()

        interval_ms = max(10, int(1000 / self.fps))
        self._timer.start(interval_ms)
        logger.info(f"Screen sharing started: target {target_id} ({target_type}), {self.res_width}x{self.res_height} @ {self.fps} FPS")

    def stop_sharing(self):
        self.is_sharing = False
        self._timer.stop()

        if self.worker:
            self.worker.stop()
            self.worker.wait(300)
            self.worker = None

        self.target_id = ""
        logger.info("Screen sharing stopped")

    def _on_timer_tick(self):
        if not self.is_sharing or not self.worker:
            return
        screen = QGuiApplication.primaryScreen()
        if not screen:
            return
        pixmap = screen.grabWindow(0)
        if not pixmap.isNull():
            self.worker.submit_frame(pixmap.toImage())

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

