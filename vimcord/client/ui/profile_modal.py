"""
User Profile Modal dialog for VimCord.
Displays custom avatar, username, ID, status, "About Me" bio, and action buttons.
"""

from typing import Dict, Any, Optional
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QWidget, QFrame
)
from vimcord.client.ui.avatar_helper import get_round_avatar_pixmap


class UserProfileModal(QDialog):
    open_dm_clicked = pyqtSignal(str, str)     # user_id, username
    start_call_clicked = pyqtSignal(str)       # user_id
    add_friend_clicked = pyqtSignal(str)       # username

    def __init__(self, user_data: Dict[str, Any], is_self: bool = False, is_friend: bool = False, parent=None):
        super().__init__(parent)
        self.user_data = user_data
        self.is_self = is_self
        self.is_friend = is_friend

        self.setWindowTitle(f"Профиль - {user_data.get('username', 'Пользователь')}")
        self.setFixedSize(340, 430)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        username = self.user_data.get("username", "Пользователь")
        user_id = self.user_data.get("user_id", "")
        avatar_color = self.user_data.get("avatar_color", "#5865F2")
        avatar_image = self.user_data.get("avatar_image", "")
        status_text = self.user_data.get("status_text", "В сети")
        is_online = self.user_data.get("online", True)

        # 1. Header Banner
        banner = QWidget()
        banner.setFixedHeight(80)
        banner.setStyleSheet(f"background-color: {avatar_color}; border-top-left-radius: 8px; border-top-right-radius: 8px;")
        main_layout.addWidget(banner)

        # 2. Content Container (Dark background)
        content_w = QWidget()
        content_w.setStyleSheet("background-color: #111214; border-bottom-left-radius: 8px; border-bottom-right-radius: 8px;")
        content_layout = QVBoxLayout(content_w)
        content_layout.setContentsMargins(18, 0, 18, 18)
        content_layout.setSpacing(10)

        # Avatar overlapping banner
        avatar_container = QHBoxLayout()
        avatar_container.setContentsMargins(0, -35, 0, 0)

        self.avatar_lbl = QLabel()
        self.avatar_lbl.setFixedSize(68, 68)
        self.avatar_lbl.setStyleSheet("""
            QLabel {
                border: 4px solid #111214;
                border-radius: 34px;
                background-color: #111214;
            }
        """)
        pixmap = get_round_avatar_pixmap(60, username, avatar_color, avatar_image)
        self.avatar_lbl.setPixmap(pixmap)
        self.avatar_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        avatar_container.addWidget(self.avatar_lbl)
        avatar_container.addStretch()

        content_layout.addLayout(avatar_container)

        # Username & tag
        name_lbl = QLabel(username)
        name_lbl.setStyleSheet("font-size: 19px; font-weight: bold; color: #ffffff;")
        content_layout.addWidget(name_lbl)

        uid_lbl = QLabel(f"ID: {user_id}")
        uid_lbl.setStyleSheet("font-size: 11px; color: #949ba4;")
        content_layout.addWidget(uid_lbl)

        # Online Status
        status_box = QHBoxLayout()
        status_box.setSpacing(6)
        dot_color = "#23a55a" if is_online else "#80848e"
        dot = QLabel("●")
        dot.setStyleSheet(f"color: {dot_color}; font-size: 14px;")
        status_lbl = QLabel(status_text or ("В сети" if is_online else "Не в сети"))
        status_lbl.setStyleSheet("color: #dbdee1; font-size: 13px;")
        status_box.addWidget(dot)
        status_box.addWidget(status_lbl)
        status_box.addStretch()
        content_layout.addLayout(status_box)

        # Divider
        div = QFrame()
        div.setFrameShape(QFrame.Shape.HLine)
        div.setStyleSheet("color: #1f2023; background-color: #1f2023; height: 1px;")
        content_layout.addWidget(div)

        # "About Me" Section
        about_title = QLabel("О СЕБЕ")
        about_title.setStyleSheet("font-size: 11px; font-weight: bold; color: #949ba4;")
        content_layout.addWidget(about_title)

        bio_content = self.user_data.get("bio", "").strip() or "Пользователь VimCord 🚀"
        about_text = QLabel(bio_content)
        about_text.setWordWrap(True)
        about_text.setStyleSheet("""
            background-color: #2b2d31;
            color: #dbdee1;
            padding: 10px;
            border-radius: 6px;
            font-size: 13px;
        """)
        content_layout.addWidget(about_text)

        content_layout.addStretch()

        # Action Buttons (only for other users)
        if not self.is_self:
            btn_layout = QHBoxLayout()
            btn_layout.setSpacing(8)

            dm_btn = QPushButton("💬 Написать")
            dm_btn.setStyleSheet("""
                QPushButton {
                    background-color: #5865F2; color: #ffffff; font-weight: bold;
                    border-radius: 4px; padding: 8px 12px; font-size: 13px; border: none;
                }
                QPushButton:hover { background-color: #4752c4; }
            """)
            dm_btn.clicked.connect(self._on_dm_clicked)
            btn_layout.addWidget(dm_btn)

            call_btn = QPushButton("📞 Позвонить")
            call_btn.setStyleSheet("""
                QPushButton {
                    background-color: #23a55a; color: #ffffff; font-weight: bold;
                    border-radius: 4px; padding: 8px 12px; font-size: 13px; border: none;
                }
                QPushButton:hover { background-color: #1f9450; }
            """)
            call_btn.clicked.connect(self._on_call_clicked)
            btn_layout.addWidget(call_btn)

            if not self.is_friend:
                friend_btn = QPushButton("➕ В друзья")
                friend_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #4e5058; color: #ffffff; font-weight: bold;
                        border-radius: 4px; padding: 8px 10px; font-size: 13px; border: none;
                    }
                    QPushButton:hover { background-color: #6d6f78; }
                """)
                friend_btn.clicked.connect(self._on_add_friend_clicked)
                btn_layout.addWidget(friend_btn)

            content_layout.addLayout(btn_layout)

        main_layout.addWidget(content_w, 1)

    def _on_dm_clicked(self):
        self.accept()
        self.open_dm_clicked.emit(self.user_data.get("user_id", ""), self.user_data.get("username", ""))

    def _on_call_clicked(self):
        self.accept()
        self.start_call_clicked.emit(self.user_data.get("user_id", ""))

    def _on_add_friend_clicked(self):
        self.accept()
        self.add_friend_clicked.emit(self.user_data.get("username", ""))
