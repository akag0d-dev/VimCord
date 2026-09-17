"""
Dedicated Screen Share Window for VimCord.
Floating, resizable window supporting fullscreen (F11), smooth video scaling, and floating controls.
"""
from typing import Optional
from PyQt6.QtCore import Qt, pyqtSignal, QEvent
from PyQt6.QtGui import QPixmap, QKeyEvent, QResizeEvent
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy
)


class ScreenShareWindow(QWidget):
    stop_stream_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.Window)
        self.setWindowTitle("VimCord - Демонстрация экрана")
        self.resize(960, 540)
        self.setMinimumSize(480, 270)
        self.setStyleSheet("background-color: #1e1f22;")

        self.streamer_name = "Пользователь"
        self.is_local = False
        self.last_pixmap: Optional[QPixmap] = None

        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 1. Top Bar
        self.top_bar = QWidget()
        self.top_bar.setFixedHeight(42)
        self.top_bar.setStyleSheet("background-color: #111214; border-bottom: 1px solid #2b2d31;")
        bar_layout = QHBoxLayout(self.top_bar)
        bar_layout.setContentsMargins(14, 0, 14, 0)
        bar_layout.setSpacing(10)

        self.title_lbl = QLabel("🖥️ Демонстрация экрана")
        self.title_lbl.setStyleSheet("color: #ffffff; font-weight: bold; font-size: 13px;")
        bar_layout.addWidget(self.title_lbl, 1)

        self.fullscreen_btn = QPushButton("⛶ Полный экран (F11)")
        self.fullscreen_btn.setStyleSheet("""
            QPushButton {
                background-color: #2b2d31; color: #dbdee1; border: none;
                border-radius: 4px; padding: 4px 10px; font-size: 12px;
            }
            QPushButton:hover { background-color: #35373c; color: #ffffff; }
        """)
        self.fullscreen_btn.clicked.connect(self.toggle_fullscreen)
        bar_layout.addWidget(self.fullscreen_btn)

        self.close_btn = QPushButton("✕ Закрыть")
        self.close_btn.setStyleSheet("""
            QPushButton {
                background-color: #f23f43; color: #ffffff; border: none;
                border-radius: 4px; padding: 4px 10px; font-size: 12px; font-weight: bold;
            }
            QPushButton:hover { background-color: #da373c; }
        """)
        self.close_btn.clicked.connect(self.close)
        bar_layout.addWidget(self.close_btn)

        main_layout.addWidget(self.top_bar)

        # 2. Video area
        self.video_label = QLabel()
        self.video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.video_label.setStyleSheet("background-color: #000000; color: #949ba4; font-size: 14px;")
        self.video_label.setText("Ожидание видеопотока...")
        main_layout.addWidget(self.video_label, 1)

    def set_streamer(self, username: str, is_local: bool = False):
        self.streamer_name = username
        self.is_local = is_local
        tag = " (Ваш экран)" if is_local else ""
        self.title_lbl.setText(f"🖥️ Демонстрация экрана: {username}{tag}")
        self.setWindowTitle(f"VimCord - Демонстрация экрана: {username}{tag}")

    def update_frame(self, pixmap: QPixmap):
        self.last_pixmap = pixmap
        if not pixmap.isNull():
            target_size = self.video_label.size()
            if target_size.width() <= 10 or target_size.height() <= 10:
                target_size = self.size()
            if target_size.width() <= 10 or target_size.height() <= 10:
                target_size = self.sizeHint()

            scaled = pixmap.scaled(
                target_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.FastTransformation
            )
            self.video_label.setPixmap(scaled)

    def resizeEvent(self, event: QResizeEvent):
        super().resizeEvent(event)
        if self.last_pixmap and not self.last_pixmap.isNull():
            self.update_frame(self.last_pixmap)

    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
            self.fullscreen_btn.setText("⛶ Полный экран (F11)")
        else:
            self.showFullScreen()
            self.fullscreen_btn.setText("⛶ Оконный режим (F11)")

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_F11:
            self.toggle_fullscreen()
        elif event.key() == Qt.Key.Key_Escape and self.isFullScreen():
            self.toggle_fullscreen()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event):
        if self.is_local:
            self.stop_stream_requested.emit()
        super().closeEvent(event)
