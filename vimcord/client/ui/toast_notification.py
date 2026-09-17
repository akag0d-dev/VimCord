"""
Toast notification widget for VimCord.
Displays unobtrusive in-app popups for incoming DMs, friend requests, and calls.
"""

from typing import Optional, Any
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QPropertyAnimation, QPoint
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QGraphicsOpacityEffect
)


class ToastNotification(QWidget):
    clicked = pyqtSignal(object)   # Emits attached custom payload

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.SubWindow | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFixedSize(300, 72)
        self.setStyleSheet("""
            #toast_card {
                background-color: #111214;
                border: 1px solid #5865F2;
                border-radius: 8px;
            }
        """)

        self.payload: Any = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)

        self._init_ui()

    def _init_ui(self):
        card = QWidget(self)
        card.setObjectName("toast_card")
        card.setGeometry(0, 0, 300, 72)

        layout = QHBoxLayout(card)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(10)

        # Icon
        self.icon_lbl = QLabel("💬")
        self.icon_lbl.setStyleSheet("font-size: 22px; background: transparent;")
        layout.addWidget(self.icon_lbl)

        # Text column
        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(2)

        self.title_lbl = QLabel("Уведомление")
        self.title_lbl.setStyleSheet("color: #ffffff; font-weight: bold; font-size: 13px; background: transparent;")
        text_layout.addWidget(self.title_lbl)

        self.msg_lbl = QLabel("Текст сообщения...")
        self.msg_lbl.setWordWrap(True)
        self.msg_lbl.setStyleSheet("color: #dbdee1; font-size: 11px; background: transparent;")
        text_layout.addWidget(self.msg_lbl)

        layout.addLayout(text_layout, 1)

        # Close button
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(20, 20)
        close_btn.setStyleSheet("""
            QPushButton {
                background: transparent; color: #949ba4; border: none; font-size: 11px;
            }
            QPushButton:hover { color: #ffffff; }
        """)
        close_btn.clicked.connect(self.hide)
        layout.addWidget(close_btn)

    def show_toast(self, title: str, message: str, icon: str = "💬", payload: Any = None, duration_ms: int = 4000):
        self.title_lbl.setText(title)
        self.msg_lbl.setText(message[:60] + ("..." if len(message) > 60 else ""))
        self.icon_lbl.setText(icon)
        self.payload = payload

        # Position at bottom-right of parent
        if self.parent():
            parent_rect = self.parent().rect()
            x = parent_rect.width() - self.width() - 20
            y = parent_rect.height() - self.height() - 20
            self.move(x, y)

        self.show()
        self.raise_()
        self._timer.start(duration_ms)

    def mousePressEvent(self, event):
        if self.payload:
            self.clicked.emit(self.payload)
        self.hide()
        super().mousePressEvent(event)
