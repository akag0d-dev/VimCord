"""
Embedded DM Call Widget for VimCord.
Occupies top ~1/3 of the DM window when in a 1-on-1 call or ringing,
displaying full antialiased circular avatar cards with green speaking halos,
real-time timer, screen share, and instant Cancel/End Call action.
"""

import time
from typing import Optional, Dict, Any
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame
)

from vimcord.client.ui.avatar_helper import RoundAvatarWidget
from vimcord.client.i18n import t


class DMParticipantCard(QWidget):
    """Card displaying a participant's circular avatar, name, and speaking state."""
    clicked = pyqtSignal(dict)

    def __init__(self, size: int = 64, parent=None):
        super().__init__(parent)
        self.user_id = ""
        self.username = ""
        self.display_name = ""
        self.avatar_color = "#5865F2"
        self.avatar_image = ""
        self.is_muted = False
        self.is_deafened = False

        self.setFixedWidth(130)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.avatar_widget = RoundAvatarWidget(size=size, parent=self)
        layout.addWidget(self.avatar_widget, alignment=Qt.AlignmentFlag.AlignCenter)

        self.name_label = QLabel()
        self.name_label.setStyleSheet("color: #ffffff; font-weight: bold; font-size: 13px;")
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.name_label)

        self.sub_label = QLabel()
        self.sub_label.setStyleSheet("color: #949ba4; font-size: 11px;")
        self.sub_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.sub_label)

    def set_user(self, user_id: str, username: str, display_name: str = "",
                 avatar_color: str = "#5865F2", avatar_image: str = "",
                 subtext: str = "", is_muted: bool = False, is_deafened: bool = False):
        self.user_id = user_id
        self.username = username
        self.display_name = display_name or username
        self.avatar_color = avatar_color
        self.avatar_image = avatar_image
        self.is_muted = is_muted
        self.is_deafened = is_deafened

        self.avatar_widget.set_user_data(
            initials=self.display_name,
            color_hex=self.avatar_color,
            base64_data=self.avatar_image
        )
        self.name_label.setText(self.display_name)
        if is_deafened:
            self.sub_label.setText("🎧 Deafened")
        elif is_muted:
            self.sub_label.setText("🔇 Muted")
        else:
            self.sub_label.setText(subtext)

    def set_speaking(self, is_speaking: bool):
        self.avatar_widget.set_speaking(is_speaking)

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit({
                "user_id": self.user_id,
                "username": self.username,
                "display_name": self.display_name,
                "avatar_color": self.avatar_color,
                "avatar_image": self.avatar_image
            })


class DMCallWidget(QWidget):
    """
    Embedded 1/3 height call widget in DM view.
    """
    end_call_clicked = pyqtSignal()
    screen_share_clicked = pyqtSignal()
    user_profile_requested = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("dm_call_widget")
        self.setFixedHeight(220)
        self.setStyleSheet("""
            QWidget#dm_call_widget {
                background-color: #1e1f22;
                border-bottom: 2px solid #232428;
            }
        """)

        self.start_time: float = 0.0
        self.is_connected: bool = False
        self.peer_id: str = ""
        self.peer_name: str = ""

        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._update_timer)

        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 10, 16, 10)
        main_layout.setSpacing(8)

        # 1. Top control bar
        top_bar = QHBoxLayout()
        top_bar.setSpacing(10)

        self.status_icon = QLabel("📞")
        self.status_icon.setStyleSheet("font-size: 16px;")
        top_bar.addWidget(self.status_icon)

        self.status_label = QLabel("Calling...")
        self.status_label.setStyleSheet("color: #ffffff; font-size: 14px; font-weight: bold;")
        top_bar.addWidget(self.status_label)

        self.duration_label = QLabel("")
        self.duration_label.setStyleSheet("color: #949ba4; font-size: 13px; font-weight: 500;")
        top_bar.addWidget(self.duration_label)

        top_bar.addStretch(1)

        # Screen Share Button
        self.screen_btn = QPushButton("🖥️ Screen")
        self.screen_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.screen_btn.setStyleSheet("""
            QPushButton {
                background-color: #35373c; color: #dbdee1; font-weight: bold;
                border-radius: 4px; padding: 6px 14px; border: none; font-size: 12px;
            }
            QPushButton:hover { background-color: #404249; color: #ffffff; }
        """)
        self.screen_btn.clicked.connect(self.screen_share_clicked.emit)
        top_bar.addWidget(self.screen_btn)

        # End / Cancel Call Button
        self.end_btn = QPushButton("End Call")
        self.end_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.end_btn.setStyleSheet("""
            QPushButton {
                background-color: #da373c; color: #ffffff; font-weight: bold;
                border-radius: 4px; padding: 6px 16px; border: none; font-size: 12px;
            }
            QPushButton:hover { background-color: #a82528; }
        """)
        self.end_btn.clicked.connect(self.end_call_clicked.emit)
        top_bar.addWidget(self.end_btn)

        main_layout.addLayout(top_bar)

        # Divider line
        div = QFrame()
        div.setFrameShape(QFrame.Shape.HLine)
        div.setStyleSheet("background-color: #2b2d31; max-height: 1px; border: none;")
        main_layout.addWidget(div)

        # 2. Centered Participant Cards stage
        cards_layout = QHBoxLayout()
        cards_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cards_layout.setSpacing(40)

        # Self card
        self.my_card = DMParticipantCard(size=64, parent=self)
        self.my_card.clicked.connect(self.user_profile_requested.emit)
        cards_layout.addWidget(self.my_card)

        # Peer card
        self.peer_card = DMParticipantCard(size=64, parent=self)
        self.peer_card.clicked.connect(self.user_profile_requested.emit)
        cards_layout.addWidget(self.peer_card)

        main_layout.addLayout(cards_layout, 1)

    def start_ringing(self, my_user: dict, peer_user: dict, is_outgoing: bool = True):
        """Sets the call widget into ringing / calling state."""
        self.is_connected = False
        self.timer.stop()
        self.duration_label.setText("")

        self.peer_id = peer_user.get("user_id", "")
        self.peer_name = peer_user.get("display_name") or peer_user.get("username", "User")

        if is_outgoing:
            self.status_label.setText(f"Calling @{self.peer_name}...")
            self.status_icon.setText("📞")
            self.end_btn.setText("Cancel Call")
        else:
            self.status_label.setText(f"Incoming Call from @{self.peer_name}...")
            self.status_icon.setText("📲")
            self.end_btn.setText("Decline")

        # Set self user
        self.my_card.set_user(
            user_id=my_user.get("user_id", ""),
            username=my_user.get("username", "You"),
            display_name=my_user.get("display_name") or my_user.get("username", "You"),
            avatar_color=my_user.get("avatar_color", "#5865F2"),
            avatar_image=my_user.get("avatar_image", ""),
            subtext="Connecting..."
        )

        # Set peer user
        self.peer_card.set_user(
            user_id=peer_user.get("user_id", ""),
            username=peer_user.get("username", "Peer"),
            display_name=self.peer_name,
            avatar_color=peer_user.get("avatar_color", "#5865F2"),
            avatar_image=peer_user.get("avatar_image", ""),
            subtext="Ringing..." if is_outgoing else "Calling you..."
        )

        self.show()

    def start_connected(self, my_user: dict, peer_user: dict):
        """Sets the call widget into active connected call state."""
        self.is_connected = True
        self.start_time = time.time()
        self.timer.start()

        self.peer_id = peer_user.get("user_id", "")
        self.peer_name = peer_user.get("display_name") or peer_user.get("username", "User")

        self.status_label.setText(f"Connected: @{self.peer_name}")
        self.status_icon.setText("🟢")
        self.end_btn.setText("End Call")
        self.duration_label.setText("00:00")

        self.my_card.set_user(
            user_id=my_user.get("user_id", ""),
            username=my_user.get("username", "You"),
            display_name=my_user.get("display_name") or my_user.get("username", "You"),
            avatar_color=my_user.get("avatar_color", "#5865F2"),
            avatar_image=my_user.get("avatar_image", ""),
            subtext="In Call",
            is_muted=my_user.get("is_muted", False),
            is_deafened=my_user.get("is_deafened", False)
        )

        self.peer_card.set_user(
            user_id=peer_user.get("user_id", ""),
            username=peer_user.get("username", "Peer"),
            display_name=self.peer_name,
            avatar_color=peer_user.get("avatar_color", "#5865F2"),
            avatar_image=peer_user.get("avatar_image", ""),
            subtext="In Call",
            is_muted=peer_user.get("is_muted", False),
            is_deafened=peer_user.get("is_deafened", False)
        )

        self.show()

    def set_user_speaking(self, user_id: str, is_speaking: bool):
        if self.my_card.user_id == user_id:
            self.my_card.set_speaking(is_speaking)
        elif self.peer_card.user_id == user_id:
            self.peer_card.set_speaking(is_speaking)

    def set_user_media_state(self, user_id: str, is_muted: bool, is_deafened: bool):
        if self.my_card.user_id == user_id:
            self.my_card.set_user(
                self.my_card.user_id, self.my_card.username, self.my_card.display_name,
                self.my_card.avatar_color, self.my_card.avatar_image,
                subtext="In Call", is_muted=is_muted, is_deafened=is_deafened
            )
        elif self.peer_card.user_id == user_id:
            self.peer_card.set_user(
                self.peer_card.user_id, self.peer_card.username, self.peer_card.display_name,
                self.peer_card.avatar_color, self.peer_card.avatar_image,
                subtext="In Call", is_muted=is_muted, is_deafened=is_deafened
            )

    def set_screen_sharing(self, is_sharing: bool):
        if is_sharing:
            self.screen_btn.setText("🔴 Stop Screen")
            self.screen_btn.setStyleSheet("""
                QPushButton {
                    background-color: #da373c; color: #ffffff; font-weight: bold;
                    border-radius: 4px; padding: 6px 14px; border: none; font-size: 12px;
                }
            """)
        else:
            self.screen_btn.setText("🖥️ Screen")
            self.screen_btn.setStyleSheet("""
                QPushButton {
                    background-color: #35373c; color: #dbdee1; font-weight: bold;
                    border-radius: 4px; padding: 6px 14px; border: none; font-size: 12px;
                }
                QPushButton:hover { background-color: #404249; color: #ffffff; }
            """)

    def stop(self):
        self.timer.stop()
        self.is_connected = False
        self.my_card.set_speaking(False)
        self.peer_card.set_speaking(False)
        self.hide()

    def _update_timer(self):
        if not self.is_connected:
            return
        elapsed = int(time.time() - self.start_time)
        m, s = divmod(elapsed, 60)
        self.duration_label.setText(f"{m:02d}:{s:02d}")
