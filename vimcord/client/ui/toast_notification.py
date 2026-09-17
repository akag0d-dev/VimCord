"""
Modern Toast notification system for VimCord.
Supports native Windows 10/11 Action Center notifications (via win11toast)
and animated, glassmorphic in-app toast cards.
"""

import os
import sys
import threading
from pathlib import Path
from typing import Optional, Any
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QPropertyAnimation, QPoint, QEasingCurve
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QGraphicsOpacityEffect, QGraphicsDropShadowEffect, QFrame
)


def show_windows_toast(title: str, message: str, icon_path: Optional[str] = None, on_click=None):
    """Dispatches a native Windows 10/11 Action Center toast asynchronously."""
    if sys.platform != "win32":
        return

    def _worker():
        try:
            from win11toast import toast
            resolved_icon = icon_path
            if not resolved_icon or not os.path.exists(resolved_icon):
                default_icon = Path(__file__).resolve().parents[3] / "icon.ico"
                if default_icon.exists():
                    resolved_icon = str(default_icon)

            kwargs = {
                "title": title,
                "body": message,
                "app_id": "VimCord",
            }
            if resolved_icon and os.path.exists(resolved_icon):
                kwargs["icon"] = resolved_icon
            if on_click:
                kwargs["on_click"] = on_click
            toast(**kwargs)
        except Exception:
            pass

    threading.Thread(target=_worker, daemon=True).start()


class ToastNotification(QWidget):
    clicked = pyqtSignal(object)   # Emits attached custom payload

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.SubWindow | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFixedSize(340, 82)

        self.payload: Any = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._fade_out)

        self._anim_pos: Optional[QPropertyAnimation] = None
        self._anim_op: Optional[QPropertyAnimation] = None

        self._init_ui()

    def _init_ui(self):
        # Card container
        self.card = QFrame(self)
        self.card.setGeometry(4, 4, 332, 74)
        self.card.setStyleSheet("""
            QFrame {
                background-color: #1e1f22;
                border: 1px solid #383a40;
                border-radius: 10px;
            }
        """)

        # Soft drop shadow
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(16)
        shadow.setColor(QColor(0, 0, 0, 150))
        shadow.setOffset(0, 4)
        self.card.setGraphicsEffect(shadow)

        layout = QHBoxLayout(self.card)
        layout.setContentsMargins(0, 0, 10, 0)
        layout.setSpacing(10)

        # 1. Left colored accent bar
        self.accent_bar = QFrame()
        self.accent_bar.setFixedWidth(5)
        self.accent_bar.setStyleSheet("""
            background-color: #5865F2;
            border-top-left-radius: 9px;
            border-bottom-left-radius: 9px;
            border: none;
        """)
        layout.addWidget(self.accent_bar)

        # 2. Icon pill
        self.icon_lbl = QLabel("💬")
        self.icon_lbl.setFixedSize(36, 36)
        self.icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_lbl.setStyleSheet("""
            QLabel {
                font-size: 20px;
                background-color: #2b2d31;
                border-radius: 18px;
                border: none;
            }
        """)
        layout.addWidget(self.icon_lbl)

        # 3. Text column
        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 8, 0, 8)
        text_layout.setSpacing(2)

        self.title_lbl = QLabel("Notification")
        self.title_lbl.setStyleSheet("color: #ffffff; font-weight: bold; font-size: 13px; border: none; background: transparent;")
        text_layout.addWidget(self.title_lbl)

        self.msg_lbl = QLabel("Message body...")
        self.msg_lbl.setWordWrap(True)
        self.msg_lbl.setStyleSheet("color: #dbdee1; font-size: 12px; border: none; background: transparent;")
        text_layout.addWidget(self.msg_lbl)

        layout.addLayout(text_layout, 1)

        # 4. Close button
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(22, 22)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet("""
            QPushButton {
                background: transparent; color: #949ba4; border: none; font-size: 11px; border-radius: 4px;
            }
            QPushButton:hover { background-color: #35373c; color: #ffffff; }
        """)
        close_btn.clicked.connect(self._fade_out)
        layout.addWidget(close_btn)

    def show_toast(self, title: str, message: str, icon: str = "💬", payload: Any = None, duration_ms: int = 4500, accent_color: str = "#5865F2"):
        self.title_lbl.setText(title)
        self.msg_lbl.setText(message[:70] + ("..." if len(message) > 70 else ""))
        self.icon_lbl.setText(icon)
        self.payload = payload
        self.accent_bar.setStyleSheet(f"""
            background-color: {accent_color};
            border-top-left-radius: 9px;
            border-bottom-left-radius: 9px;
            border: none;
        """)

        # Position at bottom-right of parent window
        if self.parent():
            parent_rect = self.parent().rect()
            final_x = parent_rect.width() - self.width() - 20
            final_y = parent_rect.height() - self.height() - 20
            start_y = final_y + 25
            self.move(final_x, start_y)

            # Slide-up animation
            self._anim_pos = QPropertyAnimation(self, b"pos")
            self._anim_pos.setDuration(220)
            self._anim_pos.setStartValue(QPoint(final_x, start_y))
            self._anim_pos.setEndValue(QPoint(final_x, final_y))
            self._anim_pos.setEasingCurve(QEasingCurve.Type.OutCubic)
            self._anim_pos.start()

        self.show()
        self.raise_()
        self._timer.start(duration_ms)

    def _fade_out(self):
        self.hide()

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        if self.payload:
            p = self.payload
            self.hide()
            self.clicked.emit(p)
