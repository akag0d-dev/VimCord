"""
Login and connection dialog for VimCord.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QMessageBox, QSpinBox
)
from vimcord.common.protocol import DEFAULT_TCP_PORT, DEFAULT_UDP_PORT


class LoginDialog(QDialog):
    def __init__(self, parent=None, default_username=""):
        super().__init__(parent)
        self.setWindowTitle("VimCord — Вход в сеть")
        self.setFixedSize(380, 420)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        self.server_host = "127.0.0.1"
        self.tcp_port = DEFAULT_TCP_PORT
        self.udp_port = DEFAULT_UDP_PORT
        self.username = default_username or "User"

        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(14)

        # App Title & Icon
        title_label = QLabel("🎙️ VimCord")
        title_label.setStyleSheet("font-size: 24px; font-weight: bold; color: #ffffff;")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)

        subtitle = QLabel("Клиент голосового и текстового общения")
        subtitle.setStyleSheet("color: #949ba4; font-size: 12px;")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle)
        layout.addSpacing(10)

        # Username
        u_label = QLabel("ИМЯ ПОЛЬЗОВАТЕЛЯ:")
        u_label.setStyleSheet("color: #b5bac1; font-weight: bold; font-size: 11px;")
        layout.addWidget(u_label)

        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Например: Alex, Bob...")
        self.username_input.setText(self.username)
        layout.addWidget(self.username_input)

        # Server Host
        host_label = QLabel("АДРЕС СЕРВЕРА:")
        host_label.setStyleSheet("color: #b5bac1; font-weight: bold; font-size: 11px;")
        layout.addWidget(host_label)

        self.host_input = QLineEdit()
        self.host_input.setText(self.server_host)
        layout.addWidget(self.host_input)

        # Port row
        port_row = QHBoxLayout()
        
        vbox_tcp = QVBoxLayout()
        tcp_label = QLabel("TCP ПОРТ:")
        tcp_label.setStyleSheet("color: #b5bac1; font-weight: bold; font-size: 11px;")
        vbox_tcp.addWidget(tcp_label)
        self.tcp_input = QSpinBox()
        self.tcp_input.setRange(1024, 65535)
        self.tcp_input.setValue(self.tcp_port)
        vbox_tcp.addWidget(self.tcp_input)
        port_row.addLayout(vbox_tcp)

        vbox_udp = QVBoxLayout()
        udp_label = QLabel("UDP ПОРТ:")
        udp_label.setStyleSheet("color: #b5bac1; font-weight: bold; font-size: 11px;")
        vbox_udp.addWidget(udp_label)
        self.udp_input = QSpinBox()
        self.udp_input.setRange(1024, 65535)
        self.udp_input.setValue(self.udp_port)
        vbox_udp.addWidget(self.udp_input)
        port_row.addLayout(vbox_udp)

        layout.addLayout(port_row)
        layout.addSpacing(10)

        # Connect button
        self.connect_btn = QPushButton("Подключиться")
        self.connect_btn.setProperty("class", "primary_btn")
        self.connect_btn.setStyleSheet("""
            background-color: #5865F2;
            color: #ffffff;
            font-size: 15px;
            font-weight: bold;
            padding: 10px;
            border-radius: 6px;
        """)
        self.connect_btn.clicked.connect(self._on_connect)
        layout.addWidget(self.connect_btn)

    def _on_connect(self):
        uname = self.username_input.text().strip()
        host = self.host_input.text().strip()
        if not uname:
            QMessageBox.warning(self, "Ошибка", "Пожалуйста, введите имя пользователя!")
            return
        if not host:
            QMessageBox.warning(self, "Ошибка", "Пожалуйста, укажите адрес сервера!")
            return

        self.username = uname
        self.server_host = host
        self.tcp_port = self.tcp_input.value()
        self.udp_port = self.udp_input.value()
        self.accept()
