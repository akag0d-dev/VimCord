"""
Voice channel and Call stage view.
Displays participant avatars with real-time green glowing speaking indicators,
and supports live Screen Sharing (video stream view and screen share toggle).
"""

from typing import Dict, List, Optional, Any
from PyQt6.QtCore import Qt, pyqtSignal, QByteArray, QTimer
from PyQt6.QtGui import QPixmap, QImage
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QGridLayout, QScrollArea
)


from vimcord.client.ui.avatar_helper import get_round_avatar_pixmap


class VoiceUserWidget(QWidget):
    clicked = pyqtSignal(dict)

    def __init__(self, username: str, user_id: str, avatar_color: str = "#5865F2", avatar_image: str = "", is_muted: bool = False, is_deafened: bool = False, parent=None):
        super().__init__(parent)
        self.username = username
        self.user_id = user_id
        self.avatar_color = avatar_color
        self.avatar_image = avatar_image
        self.is_muted = is_muted
        self.is_deafened = is_deafened
        self.is_speaking = False

        self.setFixedSize(110, 120)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Нажмите для просмотра профиля")
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Avatar circle
        self.avatar = QLabel()
        self.avatar.setFixedSize(58, 58)
        self.avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._set_avatar_style(speaking=False)
        layout.addWidget(self.avatar)

        # Username + media icon row
        name_row = QHBoxLayout()
        name_row.setSpacing(3)
        name_row.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.name_label = QLabel(self.username)
        self.name_label.setStyleSheet("color: #ffffff; font-weight: bold; font-size: 12px;")
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_row.addWidget(self.name_label)

        self.badge_label = QLabel()
        self.badge_label.setStyleSheet("font-size: 11px;")
        self._update_badge()
        name_row.addWidget(self.badge_label)

        layout.addLayout(name_row)

    def _update_badge(self):
        if self.is_deafened:
            self.badge_label.setText("🎧")
            self.badge_label.show()
        elif self.is_muted:
            self.badge_label.setText("🔇")
            self.badge_label.show()
        else:
            self.badge_label.setText("")
            self.badge_label.hide()

    def _set_avatar_style(self, speaking: bool):
        pixmap = get_round_avatar_pixmap(54, self.username, self.avatar_color, self.avatar_image)
        self.avatar.setPixmap(pixmap)
        if speaking:
            self.avatar.setStyleSheet("""
                QLabel {
                    border: 3px solid #23a55a;
                    border-radius: 29px;
                    background-color: transparent;
                }
            """)
        else:
            self.avatar.setStyleSheet("""
                QLabel {
                    border: 3px solid transparent;
                    border-radius: 29px;
                    background-color: transparent;
                }
            """)

    def set_speaking(self, speaking: bool):
        if self.is_speaking != speaking:
            self.is_speaking = speaking
            self._set_avatar_style(speaking)

    def set_media_state(self, is_muted: bool, is_deafened: bool):
        self.is_muted = is_muted
        self.is_deafened = is_deafened
        self._update_badge()

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            data = {
                "user_id": self.user_id,
                "username": self.username,
                "avatar_color": self.avatar_color,
                "avatar_image": self.avatar_image,
                "is_muted": self.is_muted,
                "is_deafened": self.is_deafened
            }
            # Emit asynchronously so that if opening a modal / switching calls
            # deletes this widget, it does not crash on a deleted C++ pointer
            QTimer.singleShot(0, lambda: self._safe_emit_clicked(data))

    def _safe_emit_clicked(self, data: dict):
        try:
            self.clicked.emit(data)
        except RuntimeError:
            pass


class VoiceView(QWidget):
    disconnect_clicked = pyqtSignal()
    screen_share_toggled = pyqtSignal(bool)  # is_sharing
    user_profile_requested = pyqtSignal(dict) # user_dict

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

    def update_participants(self, users: List[Dict[str, Any]]):
        for w in self.user_widgets.values():
            self.grid_layout.removeWidget(w)
            w.deleteLater()
        self.user_widgets.clear()

        cols = max(1, min(6, len(users)))
        for idx, u in enumerate(users):
            uid = u.get("user_id")
            uname = u.get("username", "User")
            color = u.get("avatar_color", "#5865F2")
            avatar_img = u.get("avatar_image", "")
            is_muted = u.get("is_muted", False)
            is_deaf = u.get("is_deafened", False)
            w = VoiceUserWidget(
                username=uname,
                user_id=uid,
                avatar_color=color,
                avatar_image=avatar_img,
                is_muted=is_muted,
                is_deafened=is_deaf
            )
            w.clicked.connect(self.user_profile_requested.emit)
            row = idx // cols
            col = idx % cols
            self.grid_layout.addWidget(w, row, col)
            self.user_widgets[uid] = w

    def set_user_media_state(self, user_id: str, is_muted: bool, is_deafened: bool):
        if user_id in self.user_widgets:
            self.user_widgets[user_id].set_media_state(is_muted, is_deafened)

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
