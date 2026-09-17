"""
Voice channel and Call stage view.
Displays participant avatars with real-time green glowing speaking indicators,
and supports live Screen Sharing (video stream view and screen share toggle).
"""

from typing import Dict, List, Optional, Any
from PyQt6.QtCore import Qt, pyqtSignal, QByteArray, QTimer
from PyQt6.QtGui import QPixmap, QImage
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QGridLayout, QScrollArea, QMenu,
    QSlider, QWidgetAction
)


from vimcord.client.ui.avatar_helper import get_round_avatar_pixmap


class VoiceUserWidget(QWidget):
    clicked = pyqtSignal(dict)
    right_clicked = pyqtSignal(dict, object)

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
        self.setToolTip("Click to view profile")
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
        data = {
            "user_id": self.user_id,
            "username": self.username,
            "avatar_color": self.avatar_color,
            "avatar_image": self.avatar_image,
            "is_muted": self.is_muted,
            "is_deafened": self.is_deafened
        }
        if event.button() == Qt.MouseButton.LeftButton:
            # Emit asynchronously so that if opening a modal / switching calls
            # deletes this widget, it does not crash on a deleted C++ pointer
            QTimer.singleShot(0, lambda: self._safe_emit_clicked(data))
        elif event.button() == Qt.MouseButton.RightButton:
            self.right_clicked.emit(data, event.globalPosition().toPoint())

    def _safe_emit_clicked(self, data: dict):
        try:
            self.clicked.emit(data)
        except RuntimeError:
            pass


class VoiceView(QWidget):
    disconnect_clicked = pyqtSignal()
    screen_share_toggled = pyqtSignal(bool)  # is_sharing
    user_profile_requested = pyqtSignal(dict) # user_dict
    peer_volume_changed = pyqtSignal(str, float) # user_id, volume
    peer_mute_toggled = pyqtSignal(str, bool)    # user_id, muted

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("voice_view")
        self.channel_name = ""
        self.current_user_id = ""
        self.peer_volumes: Dict[str, float] = {}
        self.peer_muted: set = set()
        self.user_widgets: Dict[str, VoiceUserWidget] = {}
        self.is_screen_sharing = False

        self._init_ui()

    def set_current_user_id(self, user_id: str):
        self.current_user_id = user_id

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

        self.title_label = QLabel("Voice Connected")
        self.title_label.setStyleSheet("color: #23a55a; font-weight: bold; font-size: 13px;")
        sb_layout.addWidget(self.title_label)

        sb_layout.addStretch(1)

        # Screen Share toggle button
        self.screen_btn = QPushButton("🖥️ Screen")
        self.screen_btn.setToolTip("Share Screen")
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
        self.disc_btn = QPushButton("Disconnect")
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

        self.screen_title = QLabel("🖥️ Screen Share")
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

        main_layout.addWidget(self.grid_container, 2)

    def set_channel_info(self, channel_name: str):
        self.channel_name = channel_name
        self.current_channel_name = channel_name
        self.title_label.setText(f"Connected: {channel_name}")

    def update_connection_info(self, ping_ms: int = 0, server_ip: str = "127.0.0.1", port: Optional[int] = None, *args, **kwargs):
        pass

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
            w.right_clicked.connect(self._on_user_right_clicked)
            row = idx // cols
            col = idx % cols
            self.grid_layout.addWidget(w, row, col)
            self.user_widgets[uid] = w

    def _on_user_right_clicked(self, user_info: dict, pos):
        user_id = user_info.get("user_id")
        if not user_id:
            return

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #111214;
                color: #dbdee1;
                border: 1px solid #232428;
                border-radius: 6px;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 24px 6px 12px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #5865F2;
                color: #ffffff;
            }
        """)

        # Profile
        profile_action = menu.addAction("👤 Profile")
        profile_action.triggered.connect(lambda: self.user_profile_requested.emit(user_info))

        # Only provide volume & mute for other users
        if user_id != self.current_user_id:
            menu.addSeparator()
            is_muted = user_id in self.peer_muted
            mute_text = "🔊 Unmute User" if is_muted else "🔇 Mute User"
            mute_action = menu.addAction(mute_text)
            mute_action.triggered.connect(lambda: self._toggle_peer_mute(user_id))

            menu.addSeparator()

            # Slider action for continuous volume (0% to 200%)
            vol_action = QWidgetAction(menu)
            slider_box = QWidget()
            slider_box.setStyleSheet("background: transparent; padding: 4px 8px;")
            s_layout = QVBoxLayout(slider_box)
            s_layout.setContentsMargins(6, 4, 6, 6)
            s_layout.setSpacing(4)

            current_pct = int(round(self.peer_volumes.get(user_id, 1.0) * 100))

            header_box = QHBoxLayout()
            vol_title = QLabel("USER VOLUME")
            vol_title.setStyleSheet("color: #949ba4; font-size: 10px; font-weight: bold; border: none;")
            vol_val_lbl = QLabel(f"{current_pct}%")
            vol_val_lbl.setStyleSheet("color: #ffffff; font-size: 11px; font-weight: bold; border: none;")
            header_box.addWidget(vol_title)
            header_box.addStretch()
            header_box.addWidget(vol_val_lbl)
            s_layout.addLayout(header_box)

            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(0, 200)
            slider.setValue(current_pct)
            slider.setStyleSheet("""
                QSlider::groove:horizontal {
                    height: 6px;
                    background: #35373c;
                    border-radius: 3px;
                }
                QSlider::sub-page:horizontal {
                    background: #5865F2;
                    border-radius: 3px;
                }
                QSlider::handle:horizontal {
                    background: #ffffff;
                    border: none;
                    width: 14px;
                    height: 14px;
                    margin: -4px 0;
                    border-radius: 7px;
                }
                QSlider::handle:horizontal:hover {
                    background: #e0e0e0;
                }
            """)
            def _on_vol_slide(val, uid=user_id, lbl=vol_val_lbl):
                lbl.setText(f"{val}%")
                self._set_peer_volume(uid, val / 100.0)

            slider.valueChanged.connect(_on_vol_slide)
            s_layout.addWidget(slider)

            vol_action.setDefaultWidget(slider_box)
            menu.addAction(vol_action)

        menu.exec(pos)

    def _toggle_peer_mute(self, user_id: str):
        if user_id in self.peer_muted:
            self.peer_muted.discard(user_id)
            self.peer_mute_toggled.emit(user_id, False)
        else:
            self.peer_muted.add(user_id)
            self.peer_mute_toggled.emit(user_id, True)

    def _set_peer_volume(self, user_id: str, volume: float):
        self.peer_volumes[user_id] = volume
        self.peer_volume_changed.emit(user_id, volume)

    def set_user_media_state(self, user_id: str, is_muted: bool, is_deafened: bool):
        if user_id in self.user_widgets:
            self.user_widgets[user_id].set_media_state(is_muted, is_deafened)

    def set_user_speaking(self, user_id: str, is_speaking: bool):
        if user_id in self.user_widgets:
            self.user_widgets[user_id].set_speaking(is_speaking)

    def _toggle_screen_share(self):
        self.is_screen_sharing = not self.is_screen_sharing
        if self.is_screen_sharing:
            self.screen_btn.setText("🔴 Stop Screen")
            self.screen_btn.setStyleSheet("""
                QPushButton {
                    background-color: #f23f43; color: white; font-weight: bold;
                    border-radius: 4px; padding: 6px 12px; border: none; font-size: 12px;
                }
            """)
        else:
            self.screen_btn.setText("🖥️ Screen")
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
            self.screen_title.setText(f"🖥️ {sender_name}'s Screen")
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
