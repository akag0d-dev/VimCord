"""
Call UI components: incoming call dialog and active 1-on-1 call banner.
"""

import time
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
)


class IncomingCallDialog(QDialog):
    accepted_signal = pyqtSignal(str)  # call_id
    declined_signal = pyqtSignal(str)  # call_id

    def __init__(self, call_id: str, from_user_id: str, from_username: str, parent=None):
        super().__init__(parent)
        self.call_id = call_id
        self.from_user_id = from_user_id
        self.from_username = from_username

        self.setWindowTitle("Входящий звонок — VimCord")
        self.setFixedSize(340, 220)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        self.setObjectName("incoming_call_dialog")

        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Phone vibrating icon
        icon = QLabel("📞")
        icon.setStyleSheet("font-size: 36px;")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon)

        # Caller label
        caller_lbl = QLabel(f"Входящий звонок от:")
        caller_lbl.setStyleSheet("color: #949ba4; font-size: 13px;")
        caller_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(caller_lbl)

        name_lbl = QLabel(self.from_username)
        name_lbl.setStyleSheet("color: #ffffff; font-size: 20px; font-weight: bold;")
        name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(name_lbl)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(14)

        self.accept_btn = QPushButton("Принять 📞")
        self.accept_btn.setObjectName("call_accept_btn")
        self.accept_btn.clicked.connect(self._on_accept)
        btn_layout.addWidget(self.accept_btn)

        self.decline_btn = QPushButton("Отклонить ❌")
        self.decline_btn.setObjectName("call_decline_btn")
        self.decline_btn.clicked.connect(self._on_decline)
        btn_layout.addWidget(self.decline_btn)

        layout.addLayout(btn_layout)

    def _on_accept(self):
        self.accepted_signal.emit(self.call_id)
        self.accept()

    def _on_decline(self):
        self.declined_signal.emit(self.call_id)
        self.reject()

    def closeEvent(self, event):
        self.declined_signal.emit(self.call_id)
        super().closeEvent(event)


class ActiveCallBanner(QWidget):
    end_call_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("active_call_banner")
        self.setFixedHeight(50)
        self.setStyleSheet("""
            QWidget#active_call_banner {
                background-color: #23a55a;
                border-radius: 6px;
                margin: 6px 12px;
            }
        """)

        self.start_time: float = 0.0
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._update_timer)

        self._init_ui()

    def _init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(12)

        icon = QLabel("📞")
        icon.setStyleSheet("font-size: 18px; color: white;")
        layout.addWidget(icon)

        self.info_lbl = QLabel("Звонок с пользователем")
        self.info_lbl.setStyleSheet("color: white; font-weight: bold; font-size: 14px;")
        layout.addWidget(self.info_lbl, 1)

        self.timer_lbl = QLabel("00:00")
        self.timer_lbl.setStyleSheet("color: white; font-size: 13px; font-weight: 500;")
        layout.addWidget(self.timer_lbl)

        self.end_btn = QPushButton("Завершить")
        self.end_btn.setStyleSheet("""
            QPushButton {
                background-color: #f23f43;
                color: white;
                font-weight: bold;
                border: none;
                border-radius: 4px;
                padding: 6px 12px;
            }
            QPushButton:hover {
                background-color: #da373c;
            }
        """)
        self.end_btn.clicked.connect(self.end_call_clicked.emit)
        layout.addWidget(self.end_btn)

    def start(self, peer_name: str):
        self.info_lbl.setText(f"Звонок: {peer_name}")
        self.start_time = time.time()
        self.timer_lbl.setText("00:00")
        self.timer.start()
        self.show()

    def stop(self):
        self.timer.stop()
        self.hide()

    def _update_timer(self):
        elapsed = int(time.time() - self.start_time)
        mins = elapsed // 60
        secs = elapsed % 60
        self.timer_lbl.setText(f"{mins:02d}:{secs:02d}")
