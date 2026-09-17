import base64
from typing import Dict, Any, Optional
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap
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

        uname = user_data.get("username", "User")
        dname = user_data.get("display_name") or uname
        self.setWindowTitle(f"Profile - {dname}")
        self.setFixedSize(360, 480)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        username = self.user_data.get("username", "User")
        display_name = self.user_data.get("display_name") or username
        user_id = self.user_data.get("user_id", "")
        avatar_color = self.user_data.get("avatar_color", "#5865F2")
        avatar_image = self.user_data.get("avatar_image", "")
        banner_color = self.user_data.get("banner_color", "#5865F2")
        banner_image = self.user_data.get("banner_image", "")
        status_text = self.user_data.get("status_text", "Online")
        is_online = self.user_data.get("online", True)

        # 1. Header Banner (Custom color or image)
        banner_lbl = QLabel()
        banner_lbl.setFixedHeight(110)
        if banner_image:
            try:
                clean_b64 = banner_image
                if "," in clean_b64:
                    clean_b64 = clean_b64.split(",", 1)[1]
                raw_bytes = base64.b64decode(clean_b64)
                pm = QPixmap()
                if pm.loadFromData(raw_bytes):
                    scaled_pm = pm.scaled(360, 110, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
                    banner_lbl.setPixmap(scaled_pm)
                    banner_lbl.setScaledContents(True)
                else:
                    banner_lbl.setStyleSheet(f"background-color: {banner_color}; border-top-left-radius: 8px; border-top-right-radius: 8px;")
            except Exception:
                banner_lbl.setStyleSheet(f"background-color: {banner_color}; border-top-left-radius: 8px; border-top-right-radius: 8px;")
        else:
            banner_lbl.setStyleSheet(f"background-color: {banner_color}; border-top-left-radius: 8px; border-top-right-radius: 8px;")
        main_layout.addWidget(banner_lbl)

        # 2. Content Container (Dark background)
        content_w = QWidget()
        content_w.setStyleSheet("background-color: #111214; border-bottom-left-radius: 8px; border-bottom-right-radius: 8px;")
        content_layout = QVBoxLayout(content_w)
        content_layout.setContentsMargins(18, 0, 18, 18)
        content_layout.setSpacing(8)

        # Enlarged avatar (84px) overlapping banner
        avatar_container = QHBoxLayout()
        avatar_container.setContentsMargins(0, -42, 0, 0)

        self.avatar_lbl = QLabel()
        self.avatar_lbl.setFixedSize(84, 84)
        self.avatar_lbl.setStyleSheet("""
            QLabel {
                border: 5px solid #111214;
                border-radius: 42px;
                background-color: #111214;
            }
        """)
        pixmap = get_round_avatar_pixmap(74, display_name, avatar_color, avatar_image)
        self.avatar_lbl.setPixmap(pixmap)
        self.avatar_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        avatar_container.addWidget(self.avatar_lbl)
        avatar_container.addStretch()

        content_layout.addLayout(avatar_container)

        # Display Name (Prominent) & @username underneath
        name_lbl = QLabel(display_name)
        name_lbl.setStyleSheet("font-size: 20px; font-weight: 800; color: #ffffff;")
        content_layout.addWidget(name_lbl)

        user_tag_lbl = QLabel(f"@{username}")
        user_tag_lbl.setStyleSheet("font-size: 13px; color: #949ba4; font-weight: 500;")
        content_layout.addWidget(user_tag_lbl)

        # Online Status
        status_box = QHBoxLayout()
        status_box.setSpacing(6)
        dot_color = "#23a55a" if is_online else "#80848e"
        dot = QLabel("●")
        dot.setStyleSheet(f"color: {dot_color}; font-size: 14px;")
        fallback_status = "Online" if is_online else "Offline"
        disp_status = status_text if status_text and status_text not in ("В сети", "Online") else fallback_status
        status_lbl = QLabel(disp_status)
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
        about_title = QLabel("ABOUT ME")
        about_title.setStyleSheet("font-size: 11px; font-weight: bold; color: #949ba4;")
        content_layout.addWidget(about_title)

        bio_content = self.user_data.get("bio", "").strip() or "VimCord user 🚀"
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

            dm_btn = QPushButton("💬 Message")
            dm_btn.setStyleSheet("""
                QPushButton {
                    background-color: #5865F2; color: #ffffff; font-weight: bold;
                    border-radius: 4px; padding: 8px 12px; font-size: 13px; border: none;
                }
                QPushButton:hover { background-color: #4752c4; }
            """)
            dm_btn.clicked.connect(self._on_dm_clicked)
            btn_layout.addWidget(dm_btn)

            if self.is_friend:
                call_btn = QPushButton("📞 Call")
                call_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #23a55a; color: #ffffff; font-weight: bold;
                        border-radius: 4px; padding: 8px 12px; font-size: 13px; border: none;
                    }
                    QPushButton:hover { background-color: #1f9450; }
                """)
                call_btn.clicked.connect(self._on_call_clicked)
                btn_layout.addWidget(call_btn)
            else:
                friend_btn = QPushButton("➕ Add Friend")
                friend_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #23a55a; color: #ffffff; font-weight: bold;
                        border-radius: 4px; padding: 8px 12px; font-size: 13px; border: none;
                    }
                    QPushButton:hover { background-color: #1f9450; }
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
