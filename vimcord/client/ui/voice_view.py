"""
Voice channel and Call stage view.
Displays participant avatars with real-time green glowing speaking indicators.
"""

from typing import Dict, List, Optional
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QGridLayout
)


class VoiceUserWidget(QWidget):
    def __init__(self, username: str, user_id: str, parent=None):
        super().__init__(parent)
        self.username = username
        self.user_id = user_id
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
        self.avatar.setFixedSize(60, 60)
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
            self.avatar.setStyleSheet("""
                background-color: #5865F2;
                color: #ffffff;
                font-size: 20px;
                font-weight: bold;
                border-radius: 30px;
                border: 3px solid #23a55a;
            """)
        else:
            self.avatar.setStyleSheet("""
                background-color: #404249;
                color: #dbdee1;
                font-size: 20px;
                font-weight: bold;
                border-radius: 30px;
                border: 3px solid transparent;
            """)

    def set_speaking(self, speaking: bool):
        if self.is_speaking != speaking:
            self.is_speaking = speaking
            self._set_avatar_style(speaking)


class VoiceView(QWidget):
    disconnect_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("voice_view")
        self.channel_name = ""
        self.user_widgets: Dict[str, VoiceUserWidget] = {}

        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 10, 12, 10)
        main_layout.setSpacing(10)

        # 1. Top status bar
        status_bar = QWidget()
        status_bar.setObjectName("voice_status_card")
        status_bar.setFixedHeight(48)
        sb_layout = QHBoxLayout(status_bar)
        sb_layout.setContentsMargins(12, 0, 12, 0)

        # Connected icon & title
        left_info = QHBoxLayout()
        icon = QLabel("🔊")
        icon.setStyleSheet("font-size: 18px;")
        left_info.addWidget(icon)

        self.title_label = QLabel("Голос подключен")
        self.title_label.setStyleSheet("color: #23a55a; font-weight: bold; font-size: 13px;")
        left_info.addWidget(self.title_label)

        badge = QLabel("24 kHz HD")
        badge.setStyleSheet("color: #949ba4; font-size: 11px; padding-left: 8px;")
        left_info.addWidget(badge)
        sb_layout.addLayout(left_info, 1)

        # Disconnect button
        self.disc_btn = QPushButton("Отключиться")
        self.disc_btn.setObjectName("disconnect_voice_btn")
        self.disc_btn.clicked.connect(self.disconnect_clicked.emit)
        sb_layout.addWidget(self.disc_btn)

        main_layout.addWidget(status_bar)

        # 2. Participants Grid Area
        self.grid_container = QWidget()
        self.grid_container.setStyleSheet("background-color: #2b2d31; border-radius: 8px;")
        self.grid_layout = QGridLayout(self.grid_container)
        self.grid_layout.setContentsMargins(20, 20, 20, 20)
        self.grid_layout.setSpacing(16)
        self.grid_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        main_layout.addWidget(self.grid_container, 1)

    def set_channel_info(self, channel_name: str):
        self.channel_name = channel_name
        self.title_label.setText(f"Подключено: {channel_name}")

    def update_participants(self, users: List[Dict[str, str]]):
        """Re-populates the participant cards in the grid."""
        # Clear existing
        for w in self.user_widgets.values():
            self.grid_layout.removeWidget(w)
            w.deleteLater()
        self.user_widgets.clear()

        # Add new
        cols = max(1, min(4, len(users)))
        for idx, u in enumerate(users):
            uid = u.get("user_id")
            uname = u.get("username", "User")
            w = VoiceUserWidget(username=uname, user_id=uid)
            row = idx // cols
            col = idx % cols
            self.grid_layout.addWidget(w, row, col)
            self.user_widgets[uid] = w

    def set_user_speaking(self, user_id: str, is_speaking: bool):
        if user_id in self.user_widgets:
            self.user_widgets[user_id].set_speaking(is_speaking)
