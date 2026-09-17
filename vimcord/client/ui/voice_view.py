"""
Voice channel and Call stage view.
Displays participant avatars with real-time green glowing speaking indicators,
and supports live Screen Sharing (video stream view and screen share toggle).
"""

from typing import Dict, List, Optional
from PyQt6.QtCore import Qt, pyqtSignal, QByteArray
from PyQt6.QtGui import QPixmap, QImage
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QGridLayout, QScrollArea
)


class VoiceUserWidget(QWidget):
    def __init__(self, username: str, user_id: str, avatar_color: str = "#5865F2", parent=None):
        super().__init__(parent)
        self.username = username
        self.user_id = user_id
        self.avatar_color = avatar_color
        self.is_speaking = False

        self.setFixedSize(110, 110)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Avatar circle
        initials = self.username[:2].upper() if self.username else "U"
        self.avatar = QLabel(initials)
        self.avatar.setFixedSize(54, 54)
        self.avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._set_avatar_style(speaking=False)
        layout.addWidget(self.avatar)

        # Username
        self.name_label = QLabel(self.username)
        self.name_label.setStyleSheet("color: #ffffff; font-weight: bold; font-size: 12px;")
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.name_label)

    def _set_avatar_style(self, speaking: bool):
        if speaking:
            self.avatar.setStyleSheet(f"""
                background-color: {self.avatar_color};
                color: #ffffff;
                font-size: 18px;
                font-weight: bold;
                border-radius: 27px;
                border: 3px solid #23a55a;
            """)
        else:
            self.avatar.setStyleSheet(f"""
                background-color: {self.avatar_color};
                color: #ffffff;
                font-size: 18px;
                font-weight: bold;
                border-radius: 27px;
                border: 3px solid transparent;
            """)

    def set_speaking(self, speaking: bool):
        if self.is_speaking != speaking:
            self.is_speaking = speaking
            self._set_avatar_style(speaking)


class VoiceView(QWidget):
    disconnect_clicked = pyqtSignal()
    screen_share_toggled = pyqtSignal(bool)  # is_sharing

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("voice_view")
        self.channel_name = ""
        self.user_widgets: Dict[str, VoiceUserWidget] = {}
        self.is_screen_sharing = False

        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 8, 12, 8)
        main_layout.setSpacing(8)

        # 1. Top status bar
        status_bar = QWidget()
        status_bar.setObjectName("voice_status_card")
        status_bar.setFixedHeight(48)
        status_bar.setStyleSheet("background-color: #232428; border-radius: 6px; padding: 4px 12px;")
        sb_layout = QHBoxLayout(status_bar)
        sb_layout.setContentsMargins(8, 0, 8, 0)
        sb_layout.setSpacing(10)

        # Title
        icon = QLabel("🔊")
        icon.setStyleSheet("font-size: 18px;")
        sb_layout.addWidget(icon)

        self.title_label = QLabel("Голос подключен")
        self.title_label.setStyleSheet("color: #23a55a; font-weight: bold; font-size: 13px;")
        sb_layout.addWidget(self.title_label)

        badge = QLabel("24 kHz HD")
        badge.setStyleSheet("color: #949ba4; font-size: 11px;")
        sb_layout.addWidget(badge)
        sb_layout.addStretch(1)

        # Screen Share toggle button
        self.screen_btn = QPushButton("🖥️ Экран")
        self.screen_btn.setToolTip("Поделиться экраном (Screen Share)")
        self.screen_btn.setStyleSheet("""
            QPushButton {
                background-color: #35373c; color: #dbdee1; font-weight: bold;
                border-radius: 4px; padding: 6px 12px; border: none; font-size: 12px;
            }
            QPushButton:hover { background-color: #404249; color: #ffffff; }
        """)
        self.screen_btn.clicked.connect(self._toggle_screen_share)
        sb_layout.addWidget(self.screen_btn)

        # Disconnect button
        self.disc_btn = QPushButton("Отключиться")
        self.disc_btn.setStyleSheet("""
            QPushButton {
                background-color: #f23f43; color: #ffffff; font-weight: bold;
                border-radius: 4px; padding: 6px 12px; border: none; font-size: 12px;
            }
            QPushButton:hover { background-color: #da373c; }
        """)
        self.disc_btn.clicked.connect(self.disconnect_clicked.emit)
        sb_layout.addWidget(self.disc_btn)

        main_layout.addWidget(status_bar)

        # 2. Live Screen Share Viewport (hidden by default)
        self.screen_container = QWidget()
        self.screen_container.setStyleSheet("background-color: #1e1f22; border-radius: 8px;")
        sc_layout = QVBoxLayout(self.screen_container)
        sc_layout.setContentsMargins(6, 6, 6, 6)

        self.screen_title = QLabel("🖥️ Демонстрация экрана")
        self.screen_title.setStyleSheet("color: #949ba4; font-size: 11px; font-weight: bold;")
        sc_layout.addWidget(self.screen_title)

        self.screen_display = QLabel()
        self.screen_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.screen_display.setMinimumHeight(240)
        self.screen_display.setStyleSheet("background-color: #000000; border-radius: 6px;")
        sc_layout.addWidget(self.screen_display, 1)

        self.screen_container.hide()
        main_layout.addWidget(self.screen_container, 1)

        # 3. Participants Grid Area
        self.grid_container = QWidget()
        self.grid_container.setStyleSheet("background-color: #2b2d31; border-radius: 8px;")
        self.grid_layout = QGridLayout(self.grid_container)
        self.grid_layout.setContentsMargins(14, 14, 14, 14)
        self.grid_layout.setSpacing(12)
        self.grid_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        main_layout.addWidget(self.grid_container)

    def set_channel_info(self, channel_name: str):
        self.channel_name = channel_name
        self.title_label.setText(f"Подключено: {channel_name}")

    def update_participants(self, users: List[Dict[str, str]]):
        for w in self.user_widgets.values():
            self.grid_layout.removeWidget(w)
            w.deleteLater()
        self.user_widgets.clear()

        cols = max(1, min(6, len(users)))
        for idx, u in enumerate(users):
            uid = u.get("user_id")
            uname = u.get("username", "User")
            color = u.get("avatar_color", "#5865F2")
            w = VoiceUserWidget(username=uname, user_id=uid, avatar_color=color)
            row = idx // cols
            col = idx % cols
            self.grid_layout.addWidget(w, row, col)
            self.user_widgets[uid] = w

    def set_user_speaking(self, user_id: str, is_speaking: bool):
        if user_id in self.user_widgets:
            self.user_widgets[user_id].set_speaking(is_speaking)

    def _toggle_screen_share(self):
        self.is_screen_sharing = not self.is_screen_sharing
        if self.is_screen_sharing:
            self.screen_btn.setText("🔴 Остановить экран")
            self.screen_btn.setStyleSheet("""
                QPushButton {
                    background-color: #f23f43; color: white; font-weight: bold;
                    border-radius: 4px; padding: 6px 12px; border: none; font-size: 12px;
                }
            """)
        else:
            self.screen_btn.setText("🖥️ Экран")
            self.screen_btn.setStyleSheet("""
                QPushButton {
                    background-color: #35373c; color: #dbdee1; font-weight: bold;
                    border-radius: 4px; padding: 6px 12px; border: none; font-size: 12px;
                }
                QPushButton:hover { background-color: #404249; color: #ffffff; }
            """)
            self.screen_container.hide()

        self.screen_share_toggled.emit(self.is_screen_sharing)

    def display_screen_frame(self, sender_name: str, jpeg_data: bytes):
        """Renders received screen share JPEG frame onto the viewport."""
        pixmap = QPixmap()
        if pixmap.loadFromData(jpeg_data, "JPEG"):
            self.screen_title.setText(f"🖥️ Экран пользователя: {sender_name}")
            scaled = pixmap.scaled(
                self.screen_display.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.screen_display.setPixmap(scaled)
            if not self.screen_container.isVisible():
                self.screen_container.show()

    def hide_screen_share(self):
        self.screen_container.hide()
        self.screen_display.clear()
