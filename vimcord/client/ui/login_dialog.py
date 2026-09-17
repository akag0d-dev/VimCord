"""
Modern login and registration dialog for VimCord.
Supports tabs for Login & Registration, password fields, and config auto-saving.
"""

import json
import os
from pathlib import Path
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QMessageBox, QSpinBox, QTabWidget, QWidget
)
from vimcord.common.protocol import DEFAULT_TCP_PORT, DEFAULT_UDP_PORT

CONFIG_FILE = Path.home() / ".vimcord_client.json"


class LoginDialog(QDialog):
    def __init__(self, parent=None, default_username=""):
        super().__init__(parent)
        self.setWindowTitle("VimCord — Авторизация")
        self.setFixedSize(400, 490)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        # Loaded config defaults
        saved_cfg = self._load_config()
        self.server_host = saved_cfg.get("host", "127.0.0.1")
        self.tcp_port = saved_cfg.get("tcp_port", DEFAULT_TCP_PORT)
        self.udp_port = saved_cfg.get("udp_port", DEFAULT_UDP_PORT)
        self.username = default_username or saved_cfg.get("username", "")
        self.password = ""
        self.action = "login"  # "login" or "register"

        self._init_ui()

    def _load_config(self) -> dict:
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_config(self):
        try:
            cfg = {
                "host": self.server_host,
                "tcp_port": self.tcp_port,
                "udp_port": self.udp_port,
                "username": self.username
            }
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 20, 24, 20)
        main_layout.setSpacing(12)

        # Header Title
        title = QLabel("🎙️ VimCord")
        title.setStyleSheet("font-size: 26px; font-weight: bold; color: #ffffff;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(title)

        subtitle = QLabel("Войдите в аккаунт или зарегистрируйтесь")
        subtitle.setStyleSheet("color: #949ba4; font-size: 12px;")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(subtitle)

        # Tabs for Login vs Register
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #35373c;
                background-color: #2b2d31;
                border-radius: 8px;
            }
            QTabBar::tab {
                background: #1e1f22;
                color: #949ba4;
                padding: 8px 24px;
                font-weight: bold;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                margin-right: 4px;
            }
            QTabBar::tab:selected {
                background: #2b2d31;
                color: #ffffff;
            }
        """)

        # Tab 1: Login
        tab_login = QWidget()
        l_layout = QVBoxLayout(tab_login)
        l_layout.setContentsMargins(18, 18, 18, 18)
        l_layout.setSpacing(10)

        l_layout.addWidget(QLabel("ИМЯ ПОЛЬЗОВАТЕЛЯ:"))
        self.login_user_input = QLineEdit()
        self.login_user_input.setPlaceholderText("Например: Alex")
        self.login_user_input.setText(self.username)
        l_layout.addWidget(self.login_user_input)

        l_layout.addWidget(QLabel("ПАРОЛЬ:"))
        self.login_pass_input = QLineEdit()
        self.login_pass_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.login_pass_input.setPlaceholderText("Введите пароль...")
        l_layout.addWidget(self.login_pass_input)

        l_btn = QPushButton("Войти в аккаунт")
        l_btn.setStyleSheet("""
            background-color: #5865F2; color: white; font-weight: bold;
            padding: 10px; border-radius: 6px; font-size: 14px; margin-top: 8px;
        """)
        l_btn.clicked.connect(self._on_login_click)
        l_layout.addWidget(l_btn)
        l_layout.addStretch(1)

        self.tabs.addTab(tab_login, "Вход")

        # Tab 2: Register
        tab_reg = QWidget()
        r_layout = QVBoxLayout(tab_reg)
        r_layout.setContentsMargins(18, 18, 18, 18)
        r_layout.setSpacing(8)

        r_layout.addWidget(QLabel("ЖЕЛАЕМЫЙ НИКНЕЙМ:"))
        self.reg_user_input = QLineEdit()
        self.reg_user_input.setPlaceholderText("Придумайте логин...")
        r_layout.addWidget(self.reg_user_input)

        r_layout.addWidget(QLabel("ПАРОЛЬ (от 4 символов):"))
        self.reg_pass_input = QLineEdit()
        self.reg_pass_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.reg_pass_input.setPlaceholderText("Придумайте пароль...")
        r_layout.addWidget(self.reg_pass_input)

        r_layout.addWidget(QLabel("ПОВТОРИТЕ ПАРОЛЬ:"))
        self.reg_pass2_input = QLineEdit()
        self.reg_pass2_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.reg_pass2_input.setPlaceholderText("Повторите пароль...")
        r_layout.addWidget(self.reg_pass2_input)

        r_btn = QPushButton("Создать аккаунт")
        r_btn.setStyleSheet("""
            background-color: #23a55a; color: white; font-weight: bold;
            padding: 10px; border-radius: 6px; font-size: 14px; margin-top: 4px;
        """)
        r_btn.clicked.connect(self._on_register_click)
        r_layout.addWidget(r_btn)
        r_layout.addStretch(1)

        self.tabs.addTab(tab_reg, "Регистрация")
        main_layout.addWidget(self.tabs, 1)

        # Server Settings Row (Host & Ports)
        srv_box = QWidget()
        srv_layout = QHBoxLayout(srv_box)
        srv_layout.setContentsMargins(0, 4, 0, 0)
        srv_layout.setSpacing(8)

        v_host = QVBoxLayout()
        v_host.addWidget(QLabel("АДРЕС СЕРВЕРА:"))
        self.host_input = QLineEdit()
        self.host_input.setText(self.server_host)
        v_host.addWidget(self.host_input)
        srv_layout.addLayout(v_host, 2)

        v_port = QVBoxLayout()
        v_port.addWidget(QLabel("ПОРТ:"))
        self.port_input = QSpinBox()
        self.port_input.setRange(1024, 65535)
        self.port_input.setValue(self.tcp_port)
        v_port.addWidget(self.port_input)
        srv_layout.addLayout(v_port, 1)

        main_layout.addWidget(srv_box)

    def _on_login_click(self):
        uname = self.login_user_input.text().strip()
        passwd = self.login_pass_input.text().strip()
        host = self.host_input.text().strip()
        if not uname:
            QMessageBox.warning(self, "Ошибка", "Введите имя пользователя!")
            return
        if not host:
            QMessageBox.warning(self, "Ошибка", "Укажите адрес сервера!")
            return

        self.action = "login"
        self.username = uname
        self.password = passwd
        self.server_host = host
        self.tcp_port = self.port_input.value()
        self.udp_port = self.tcp_port + 1
        self._save_config()
        self.accept()

    def _on_register_click(self):
        uname = self.reg_user_input.text().strip()
        p1 = self.reg_pass_input.text().strip()
        p2 = self.reg_pass2_input.text().strip()
        host = self.host_input.text().strip()

        if not uname or len(uname) < 2:
            QMessageBox.warning(self, "Ошибка", "Имя пользователя должно быть не менее 2 символов!")
            return
        if not p1 or len(p1) < 4:
            QMessageBox.warning(self, "Ошибка", "Пароль должен быть не менее 4 символов!")
            return
        if p1 != p2:
            QMessageBox.warning(self, "Ошибка", "Пароли не совпадают!")
            return
        if not host:
            QMessageBox.warning(self, "Ошибка", "Укажите адрес сервера!")
            return

        self.action = "register"
        self.username = uname
        self.password = p1
        self.server_host = host
        self.tcp_port = self.port_input.value()
        self.udp_port = self.tcp_port + 1
        self._save_config()
        self.accept()
