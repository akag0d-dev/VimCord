"""
User panel widget at the bottom of the sidebar (avatar, mute, deafen, settings).
"""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton
)
from vimcord.client.ui.avatar_helper import get_round_avatar_pixmap


class UserPanel(QWidget):
    mic_toggled = pyqtSignal(bool)       # is_muted
    deafen_toggled = pyqtSignal(bool)    # is_deafened
    settings_clicked = pyqtSignal()
    profile_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("user_panel_widget")
        self.setFixedHeight(54)
        
        self.is_muted = False
        self.is_deafened = False
        self.username = "User"
        self.user_id = ""
        self.avatar_color = "#5865F2"
        self.avatar_image = ""
        self.status_text = "Online"

        self._init_ui()

    def _init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(6)

        # Avatar and user info clickable container
        profile_btn = QWidget()
        profile_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        profile_btn.setStyleSheet("""
            QWidget:hover {
                background-color: #35373c;
                border-radius: 4px;
            }
        """)
        p_layout = QHBoxLayout(profile_btn)
        p_layout.setContentsMargins(4, 2, 4, 2)
        p_layout.setSpacing(6)

        # Avatar circle
        self.avatar_label = QLabel()
        self.avatar_label.setFixedSize(36, 36)
        self.avatar_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        p_layout.addWidget(self.avatar_label)

        # Username & status
        info_layout = QVBoxLayout()
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(1)

        self.name_label = QLabel(self.username)
        self.name_label.setStyleSheet("font-weight: bold; color: #ffffff; font-size: 13px; background: transparent;")
        info_layout.addWidget(self.name_label)

        self.status_label = QLabel("Online")
        self.status_label.setStyleSheet("color: #23a55a; font-size: 11px; background: transparent;")
        info_layout.addWidget(self.status_label)

        p_layout.addLayout(info_layout, 1)
        profile_btn.mousePressEvent = lambda e: self.profile_clicked.emit()
        layout.addWidget(profile_btn, 1)

        # Action buttons
        btn_style_normal = """
            QPushButton {
                background: transparent;
                border-radius: 4px;
                font-size: 16px;
                border: none;
                min-width: 28px;
                max-width: 28px;
                min-height: 28px;
                max-height: 28px;
            }
            QPushButton:hover {
                background-color: #35373c;
            }
        """
        btn_style_active = """
            QPushButton {
                background-color: #f23f43;
                border-radius: 4px;
                font-size: 16px;
                border: none;
                min-width: 28px;
                max-width: 28px;
                min-height: 28px;
                max-height: 28px;
            }
        """

        # Mic button
        self.mic_btn = QPushButton("🎙️")
        self.mic_btn.setToolTip("Mute Microphone")
        self.mic_btn.setStyleSheet(btn_style_normal)
        self.mic_btn.clicked.connect(self._toggle_mic)
        layout.addWidget(self.mic_btn)

        # Deafen button
        self.deafen_btn = QPushButton("🎧")
        self.deafen_btn.setToolTip("Deafen Audio")
        self.deafen_btn.setStyleSheet(btn_style_normal)
        self.deafen_btn.clicked.connect(self._toggle_deafen)
        layout.addWidget(self.deafen_btn)

        # Settings button
        self.settings_btn = QPushButton("⚙️")
        self.settings_btn.setToolTip("User Settings")
        self.settings_btn.setStyleSheet(btn_style_normal)
        self.settings_btn.clicked.connect(self.settings_clicked.emit)
        layout.addWidget(self.settings_btn)

    def set_user(self, username: str, user_id: str, avatar_color: str = "#5865F2", status_text: str = "Online", avatar_image: str = "", display_name: str = ""):
        self.username = username
        self.display_name = display_name or username
        self.user_id = user_id
        self.avatar_color = avatar_color
        self.avatar_image = avatar_image
        self.status_text = status_text
        self.name_label.setText(self.display_name)
        self.status_label.setText(status_text or "Online")
        pixmap = get_round_avatar_pixmap(36, self.display_name, avatar_color, avatar_image)
        self.avatar_label.setPixmap(pixmap)
        self.avatar_label.setStyleSheet("background: transparent; border: none;")

    def set_speaking(self, is_speaking: bool):
        if is_speaking:
            self.avatar_label.setStyleSheet("""
                QLabel {
                    border: 2px solid #23a55a;
                    border-radius: 18px;
                    background-color: transparent;
                }
            """)
        else:
            self.avatar_label.setStyleSheet("background: transparent; border: none;")

    def _toggle_mic(self):
        self.is_muted = not self.is_muted
        if self.is_muted:
            self.mic_btn.setText("🔇")
            self.mic_btn.setStyleSheet("""
                background-color: #f23f43;
                border-radius: 4px;
                font-size: 16px;
                border: none;
                min-width: 28px;
                max-width: 28px;
                min-height: 28px;
                max-height: 28px;
            """)
        else:
            self.mic_btn.setText("🎙️")
            self.mic_btn.setStyleSheet("""
                QPushButton {
                    background: transparent;
                    border-radius: 4px;
                    font-size: 16px;
                    border: none;
                    min-width: 28px;
                    max-width: 28px;
                    min-height: 28px;
                    max-height: 28px;
                }
                QPushButton:hover {
                    background-color: #35373c;
                }
            """)
        self.mic_toggled.emit(self.is_muted)

    def _toggle_deafen(self):
        self.is_deafened = not self.is_deafened
        if self.is_deafened:
            self.deafen_btn.setText("🔇")
            self.deafen_btn.setStyleSheet("""
                background-color: #f23f43;
                border-radius: 4px;
                font-size: 16px;
                border: none;
                min-width: 28px;
                max-width: 28px;
                min-height: 28px;
                max-height: 28px;
            """)
        else:
            self.deafen_btn.setText("🎧")
            self.deafen_btn.setStyleSheet("""
                QPushButton {
                    background: transparent;
                    border-radius: 4px;
                    font-size: 16px;
                    border: none;
                    min-width: 28px;
                    max-width: 28px;
                    min-height: 28px;
                    max-height: 28px;
                }
                QPushButton:hover {
                    background-color: #35373c;
                }
            """)
        self.deafen_toggled.emit(self.is_deafened)
