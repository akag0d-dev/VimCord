"""
Screen Sharing capture and streaming engine for VimCord.
Uses PyQt6 native screen grabbing and compressed JPEG frames over UDP.
"""

import logging
import time
from typing import Optional, Callable
from PyQt6.QtCore import QObject, QTimer, pyqtSignal, QByteArray, QBuffer, QIODevice, Qt
from PyQt6.QtGui import QGuiApplication, QPixmap
from vimcord.common.protocol import pack_udp_audio, UDP_TYPE_SCREEN_FRAME

logger = logging.getLogger("VimCord.ScreenShare")


class ScreenCapturer(QObject):
    frame_captured = pyqtSignal(bytes)  # Emits raw JPEG bytes for local preview or transmission

    def __init__(self, send_func: Optional[Callable[[bytes], None]] = None, parent=None):
        super().__init__(parent)
        self.send_func = send_func
        self.on_frame_ready: Optional[Callable[[str, str, bytes], None]] = None
        self.is_sharing: bool = False
        self.user_id: str = ""
        self.target_id: str = ""
        self.target_type: str = "channel"
        self._seq: int = 0

        self.res_width: int = 800
        self.res_height: int = 450
        self.fps: int = 15
        self.quality: int = 45

        # Capture timer running at configurable FPS
        self.timer = QTimer(self)
        self.timer.setInterval(int(1000 / self.fps))
        self.timer.timeout.connect(self._capture_frame)

    def set_stream_settings(self, resolution: str = "720p", fps: int = 15, quality: int = 45):
        """Sets resolution preset ('360p', '480p', '720p', '1080p'), FPS, and JPEG quality."""
        resolutions = {
            "360p": (640, 360),
            "480p": (854, 480),
            "720p": (1280, 720),
            "1080p": (1920, 1080)
        }
        w, h = resolutions.get(resolution, (800, 450))
        self.res_width = w
        self.res_height = h
        self.fps = max(5, min(30, fps))
        self.quality = max(20, min(85, quality))
        self.timer.setInterval(int(1000 / self.fps))
        logger.info(f"Screen share settings updated: {w}x{h}, {self.fps} FPS, quality {self.quality}")

    def start_sharing(self, user_id: str, target_id: str, target_type: str = "channel"):
        self.user_id = user_id
        self.target_id = target_id
        self.target_type = target_type
        self.is_sharing = True
        self.timer.start()
        logger.info(f"Screen sharing started for target: {target_id} ({target_type})")

    def stop_sharing(self):
        self.is_sharing = False
        self.timer.stop()
        self.target_id = ""
        logger.info("Screen sharing stopped")

    def _capture_frame(self):
        if not self.is_sharing or not self.user_id or not self.target_id:
            return

        screen = QGuiApplication.primaryScreen()
        if not screen:
            return

        # Grab primary desktop window
        pixmap = screen.grabWindow(0)
        if pixmap.isNull():
            return

        scaled = pixmap.scaled(
            self.res_width, self.res_height,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.FastTransformation
        )

        byte_arr = QByteArray()
        buffer = QBuffer(byte_arr)
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        scaled.save(buffer, "JPEG", self.quality)
        jpeg_data = byte_arr.data()

        if not jpeg_data or len(jpeg_data) > 65000:
            return

        if self.on_frame_ready:
            self.on_frame_ready(self.target_type, self.target_id, jpeg_data)
        elif self.send_func:
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
