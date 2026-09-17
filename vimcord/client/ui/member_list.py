"""
Right-side Member List sidebar for VimCord.
Displays room members separated by Online / Offline status with avatars and context actions.
"""

from typing import List, Dict, Any, Optional
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QPainter, QColor, QBrush, QPixmap, QCursor
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea,
    QFrame, QMenu, QSlider
)


class MemberItemWidget(QWidget):
    clicked = pyqtSignal(str) # user_id
    right_clicked = pyqtSignal(str, object) # user_id, global_pos

    def __init__(self, user_info: Dict[str, Any], parent=None):
        super().__init__(parent)
        self.user_info = user_info
        self.user_id = user_info.get("user_id", "")
        self.username = user_info.get("username", "User")
        self.status_text = user_info.get("status_text", "")
        self.avatar_color = user_info.get("avatar_color", "#5865F2")
        self.avatar_image = user_info.get("avatar_image", "")
        self.is_online = bool(user_info.get("online", False))
        self.is_hovered = False

        self.setFixedHeight(44)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._init_ui()

    def _init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(10)

        # Avatar container with status dot
        self.avatar_label = QLabel()
        self.avatar_label.setFixedSize(32, 32)
        self._render_avatar()
        layout.addWidget(self.avatar_label)

        # Name and status layout
        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(1)

        self.name_label = QLabel(self.username)
        name_color = "#f2f3f5" if self.is_online else "#80848e"
        self.name_label.setStyleSheet(f"color: {name_color}; font-weight: 600; font-size: 13px;")
        text_layout.addWidget(self.name_label)

        if self.status_text:
            self.status_label = QLabel(self.status_text)
            self.status_label.setStyleSheet("color: #949ba4; font-size: 11px;")
            text_layout.addWidget(self.status_label)

        layout.addLayout(text_layout, 1)

    def _render_avatar(self):
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw base avatar
        if self.avatar_image:
            import base64
            from PyQt6.QtCore import QByteArray
            try:
                img_data = base64.b64decode(self.avatar_image)
                raw_pm = QPixmap()
                raw_pm.loadFromData(QByteArray(img_data))
                if not raw_pm.isNull():
                    scaled_pm = raw_pm.scaled(32, 32, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
                    painter.setBrush(QBrush(scaled_pm))
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.drawEllipse(0, 0, 32, 32)
                else:
                    self._draw_fallback_avatar(painter)
            except Exception:
                self._draw_fallback_avatar(painter)
        else:
            self._draw_fallback_avatar(painter)

        # Draw status dot
        dot_color = QColor("#23a55a") if self.is_online else QColor("#80848e")
        painter.setBrush(QBrush(dot_color))
        painter.setPen(QColor("#2b2d31"))
        painter.drawEllipse(22, 22, 9, 9)

        painter.end()
        self.avatar_label.setPixmap(pixmap)

    def _draw_fallback_avatar(self, painter: QPainter):
        painter.setBrush(QBrush(QColor(self.avatar_color)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(0, 0, 32, 32)

        painter.setPen(QColor("#ffffff"))
        font = painter.font()
        font.setBold(True)
        font.setPixelSize(13)
        painter.setFont(font)
        initials = self.username[:2].upper() if self.username else "U"
        painter.drawText(0, 0, 32, 32, Qt.AlignmentFlag.AlignCenter, initials)

    def enterEvent(self, event):
        self.is_hovered = True
        self.setStyleSheet("background-color: #35373c; border-radius: 4px;")
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.is_hovered = False
        self.setStyleSheet("background-color: transparent;")
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.user_id)
        elif event.button() == Qt.MouseButton.RightButton:
            self.right_clicked.emit(self.user_id, event.globalPosition().toPoint())
        super().mousePressEvent(event)


class MemberListWidget(QWidget):
    view_profile_requested = pyqtSignal(str)          # user_id
    open_dm_requested = pyqtSignal(str, str)           # user_id, username
    call_requested = pyqtSignal(str)                  # user_id
    peer_volume_changed = pyqtSignal(str, float)      # user_id, volume
    peer_mute_toggled = pyqtSignal(str, bool)         # user_id, muted

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_room_id: str = "room-default"
        self.members: List[Dict[str, Any]] = []
        self.peer_volumes: Dict[str, float] = {}
        self.peer_muted: set = set()
        self.current_user_id: str = ""

        self.setFixedWidth(240)
        self.setStyleSheet("background-color: #2b2d31; border-left: 1px solid #1f2023;")
        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Header
        header = QWidget()
        header.setFixedHeight(48)
        header.setStyleSheet("border-bottom: 1px solid #1f2023; padding-left: 16px;")
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(16, 0, 16, 0)
        
        self.title_label = QLabel("УЧАСТНИКИ")
        self.title_label.setStyleSheet("color: #949ba4; font-size: 12px; font-weight: 700; letter-spacing: 0.5px;")
        h_layout.addWidget(self.title_label)
        main_layout.addWidget(header)

        # Scrollable member list container
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet("""
            QScrollArea { border: none; background-color: #2b2d31; }
            QScrollBar:vertical {
                background: #2b2d31;
                width: 6px;
                margin: 0;
            }
            QScrollBar::handle:vertical {
                background: #1a1b1e;
                border-radius: 3px;
                min-height: 20px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)

        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(8, 12, 8, 12)
        self.content_layout.setSpacing(4)
        self.content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.scroll.setWidget(self.content_widget)
        main_layout.addWidget(self.scroll, 1)

    def set_current_user_id(self, user_id: str):
        self.current_user_id = user_id

    def set_members(self, room_id: str, members: List[Dict[str, Any]]):
        self.current_room_id = room_id
        self.members = members
        self._rebuild_list()

    def update_presence(self, user_id: str, online: bool, status_text: Optional[str] = None):
        for m in self.members:
            if m["user_id"] == user_id:
                m["online"] = online
                if status_text is not None:
                    m["status_text"] = status_text
                break
        self._rebuild_list()

    def _rebuild_list(self):
        # Clear existing items
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        online_members = [m for m in self.members if m.get("online", False)]
        offline_members = [m for m in self.members if not m.get("online", False)]

        # Sort alphabetically
        online_members.sort(key=lambda x: x.get("username", "").lower())
        offline_members.sort(key=lambda x: x.get("username", "").lower())

        # 1. Online Section
        if online_members:
            sec_label = QLabel(f"В СЕТИ — {len(online_members)}")
            sec_label.setStyleSheet("color: #949ba4; font-size: 11px; font-weight: 700; padding: 6px 8px 4px 8px;")
            self.content_layout.addWidget(sec_label)

            for m in online_members:
                item_w = MemberItemWidget(m)
                item_w.clicked.connect(self._on_member_clicked)
                item_w.right_clicked.connect(self._on_member_right_clicked)
                self.content_layout.addWidget(item_w)

        # 2. Offline Section
        if offline_members:
            sec_label = QLabel(f"НЕ В СЕТИ — {len(offline_members)}")
            sec_label.setStyleSheet("color: #949ba4; font-size: 11px; font-weight: 700; padding: 12px 8px 4px 8px;")
            self.content_layout.addWidget(sec_label)

            for m in offline_members:
                item_w = MemberItemWidget(m)
                item_w.clicked.connect(self._on_member_clicked)
                item_w.right_clicked.connect(self._on_member_right_clicked)
                self.content_layout.addWidget(item_w)

        self.title_label.setText(f"УЧАСТНИКИ ({len(self.members)})")

    def _on_member_clicked(self, user_id: str):
        self.view_profile_requested.emit(user_id)

    def _on_member_right_clicked(self, user_id: str, pos):
        user_info = next((m for m in self.members if m["user_id"] == user_id), None)
        if not user_info:
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

        # 1. Profile action
        profile_action = menu.addAction("👤 Профиль")
        profile_action.triggered.connect(lambda: self.view_profile_requested.emit(user_id))

        # Only offer DM and Call if not self
        if user_id != self.current_user_id:
            menu.addSeparator()
            dm_action = menu.addAction("💬 Написать сообщение")
            dm_action.triggered.connect(lambda: self.open_dm_requested.emit(user_id, user_info["username"]))

            call_action = menu.addAction("📞 Позвонить")
            call_action.triggered.connect(lambda: self.call_requested.emit(user_id))

            menu.addSeparator()

            # Local mute toggle
            is_muted = user_id in self.peer_muted
            mute_text = "🔊 Включить звук пользователя" if is_muted else "🔇 Заглушить пользователя"
            mute_action = menu.addAction(mute_text)
            mute_action.triggered.connect(lambda: self._toggle_peer_mute(user_id))

            # Submenu for Volume
            vol_menu = menu.addMenu("🎚️ Громкость пользователя")
            current_vol = self.peer_volumes.get(user_id, 1.0)
            
            for pct in [50, 100, 150, 200]:
                check = " ✓" if abs(current_vol - (pct / 100.0)) < 0.05 else ""
                act = vol_menu.addAction(f"{pct}%{check}")
                val = pct / 100.0
                act.triggered.connect(lambda checked=False, u=user_id, v=val: self._set_peer_volume(u, v))

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
