"""
VoiceConnectedBar widget positioned above the UserPanel in the sidebar.
Shows active voice connection status, channel name, and quick disconnect/screen share buttons.
"""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton
)


class VoiceConnectedBar(QWidget):
    disconnect_clicked = pyqtSignal()
    screen_share_clicked = pyqtSignal()
    channel_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("voice_connected_bar")
        self.setFixedHeight(54)
        self.setStyleSheet("""
            #voice_connected_bar {
                background-color: #111214;
                border-top: 1px solid #1f2023;
                border-bottom: 1px solid #1f2023;
            }
        """)

        self.is_sharing = False
        self._init_ui()

    def _init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(8)

        # Info column (Status + Channel)
        info_layout = QVBoxLayout()
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(1)

        # Status text with green dot
        self.status_lbl = QLabel("●  Голос подключен")
        self.status_lbl.setStyleSheet("color: #23a55a; font-size: 11px; font-weight: bold;")
        info_layout.addWidget(self.status_lbl)

        # Channel name button/label
        self.channel_btn = QPushButton("🔊 Голосовой канал")
        self.channel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.channel_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #949ba4;
                font-size: 12px;
                text-align: left;
                border: none;
                padding: 0px;
            }
            QPushButton:hover {
                color: #ffffff;
                text-decoration: underline;
            }
        """)
        self.channel_btn.clicked.connect(self.channel_clicked.emit)
        info_layout.addWidget(self.channel_btn)

        layout.addLayout(info_layout, 1)

        # Screen Share button
        self.screen_btn = QPushButton("🖥️")
        self.screen_btn.setToolTip("Демонстрация экрана")
        self.screen_btn.setFixedSize(30, 30)
        self.screen_btn.setStyleSheet("""
            QPushButton {
                background: #2b2d31;
                border-radius: 4px;
                font-size: 14px;
                border: none;
            }
            QPushButton:hover {
                background-color: #35373c;
            }
        """)
        self.screen_btn.clicked.connect(self.screen_share_clicked.emit)
        layout.addWidget(self.screen_btn)

        # Disconnect button
        self.disconnect_btn = QPushButton("📞")
        self.disconnect_btn.setToolTip("Отключиться от голосового канала")
        self.disconnect_btn.setFixedSize(30, 30)
        self.disconnect_btn.setStyleSheet("""
            QPushButton {
                background: #f23f43;
                border-radius: 4px;
                font-size: 14px;
                color: #ffffff;
                border: none;
            }
            QPushButton:hover {
                background-color: #da373c;
            }
        """)
        self.disconnect_btn.clicked.connect(self.disconnect_clicked.emit)
        layout.addWidget(self.disconnect_btn)

    def set_channel(self, room_name: str, channel_name: str):
        clean_name = channel_name.lstrip("🔊 ").strip()
        display_text = f"🔊 {clean_name}"
        if room_name and room_name != "Главный Сервер":
            display_text += f" / {room_name}"
        self.channel_btn.setText(display_text)
        self.channel_btn.setToolTip(f"{channel_name} ({room_name})")

    def set_screen_sharing(self, is_sharing: bool):
        self.is_sharing = is_sharing
        if is_sharing:
            self.screen_btn.setStyleSheet("""
                QPushButton {
                    background-color: #23a55a;
                    border-radius: 4px;
                    font-size: 14px;
                    border: none;
                }
                QPushButton:hover {
                    background-color: #1f9450;
                }
            """)
            self.screen_btn.setToolTip("Остановить демонстрацию экрана")
        else:
            self.screen_btn.setStyleSheet("""
                QPushButton {
                    background: #2b2d31;
                    border-radius: 4px;
                    font-size: 14px;
                    border: none;
                }
                QPushButton:hover {
                    background-color: #35373c;
                }
            """)
            self.screen_btn.setToolTip("Демонстрация экрана")
