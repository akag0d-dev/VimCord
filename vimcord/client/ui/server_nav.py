"""
Server navigation rail (leftmost Discord-like server list).
"""

from typing import Dict, Any, List
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QScrollArea, QFrame
)


class ServerNavBar(QWidget):
    dm_selected = pyqtSignal()
    room_selected = pyqtSignal(str)  # room_id
    create_room_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("server_nav_bar")
        self.setFixedWidth(72)
        
        self.room_buttons: Dict[str, QPushButton] = {}
        self.active_id: str = "@me"  # "@me" = direct messages, or room_id

        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(8)
        main_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)

        # 1. Direct Messages Button (Discord Home / @me)
        self.dm_btn = QPushButton("💬")
        self.dm_btn.setToolTip("Личные сообщения и друзья")
        self.dm_btn.setFixedSize(48, 48)
        self.dm_btn.setStyleSheet("""
            QPushButton {
                background-color: #5865F2;
                color: #ffffff;
                font-size: 20px;
                border-radius: 24px;
                border: none;
            }
            QPushButton:hover {
                border-radius: 16px;
            }
        """)
        self.dm_btn.clicked.connect(self._on_dm_clicked)
        main_layout.addWidget(self.dm_btn)

        # Separator line
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFixedHeight(2)
        sep.setStyleSheet("background-color: #35373c; margin: 4px 6px;")
        main_layout.addWidget(sep)

        # 2. Scroll area for server/room icons
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("background: transparent; border: none;")

        self.rooms_container = QWidget()
        self.rooms_container.setStyleSheet("background: transparent;")
        self.rooms_layout = QVBoxLayout(self.rooms_container)
        self.rooms_layout.setContentsMargins(0, 0, 0, 0)
        self.rooms_layout.setSpacing(8)
        self.rooms_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)

        scroll.setWidget(self.rooms_container)
        main_layout.addWidget(scroll, 1)

        # 3. Add Server Button (+)
        self.add_btn = QPushButton("+")
        self.add_btn.setToolTip("Создать сервер (комнату)")
        self.add_btn.setFixedSize(48, 48)
        self.add_btn.setStyleSheet("""
            QPushButton {
                background-color: #313338;
                color: #23a55a;
                font-size: 26px;
                font-weight: bold;
                border-radius: 24px;
                border: none;
            }
            QPushButton:hover {
                background-color: #23a55a;
                color: #ffffff;
                border-radius: 16px;
            }
        """)
        self.add_btn.clicked.connect(self.create_room_requested.emit)
        main_layout.addWidget(self.add_btn)

    def _on_dm_clicked(self):
        self.set_active("@me")
        self.dm_selected.emit()

    def set_rooms(self, rooms: List[Dict[str, Any]]):
        """Re-renders the list of rooms in the rail."""
        # Clear existing buttons
        for btn in self.room_buttons.values():
            self.rooms_layout.removeWidget(btn)
            btn.deleteLater()
        self.room_buttons.clear()

        for r in rooms:
            self.add_room_button(r)

    def add_room_button(self, room: Dict[str, Any]):
        r_id = room.get("room_id")
        r_name = room.get("name", "Сервер")
        
        # Make initials
        words = r_name.split()
        initials = "".join([w[0].upper() for w in words[:2]]) if words else "С"

        btn = QPushButton(initials)
        btn.setToolTip(r_name)
        btn.setFixedSize(48, 48)
        btn.setProperty("room_id", r_id)
        self._update_button_style(btn, active=(r_id == self.active_id))

        btn.clicked.connect(lambda checked, rid=r_id: self._on_room_btn_clicked(rid))
        self.rooms_layout.addWidget(btn)
        self.room_buttons[r_id] = btn

    def remove_room_button(self, room_id: str):
        btn = self.room_buttons.pop(room_id, None)
        if btn:
            self.rooms_layout.removeWidget(btn)
            btn.deleteLater()

    def set_active(self, target_id: str):
        self.active_id = target_id
        # Update DM button style
        if target_id == "@me":
            self.dm_btn.setStyleSheet("""
                background-color: #5865F2;
                color: #ffffff;
                font-size: 20px;
                border-radius: 16px;
                border: none;
            """)
        else:
            self.dm_btn.setStyleSheet("""
                QPushButton {
                    background-color: #313338;
                    color: #dbdee1;
                    font-size: 20px;
                    border-radius: 24px;
                    border: none;
                }
                QPushButton:hover {
                    background-color: #5865F2;
                    color: #ffffff;
                    border-radius: 16px;
                }
            """)

        # Update room buttons style
        for rid, btn in self.room_buttons.items():
            self._update_button_style(btn, active=(rid == target_id))

    def _update_button_style(self, btn: QPushButton, active: bool):
        if active:
            btn.setStyleSheet("""
                background-color: #5865F2;
                color: #ffffff;
                font-weight: bold;
                font-size: 15px;
                border-radius: 16px;
                border: none;
            """)
        else:
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #313338;
                    color: #dbdee1;
                    font-weight: bold;
                    font-size: 15px;
                    border-radius: 24px;
                    border: none;
                }
                QPushButton:hover {
                    background-color: #5865F2;
                    color: #ffffff;
                    border-radius: 16px;
                }
            """)

    def _on_room_btn_clicked(self, room_id: str):
        self.set_active(room_id)
        self.room_selected.emit(room_id)
