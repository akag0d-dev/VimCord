"""
Modern login and registration dialog for VimCord.
Supports tabs for Login & Registration, AppData configuration persistence,
auto-login preference, and icon branding.
"""

from pathlib import Path
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QMessageBox, QSpinBox, QTabWidget, QWidget, QCheckBox
)
from vimcord.client.config import load_config, save_config
from vimcord.common.protocol import DEFAULT_TCP_PORT, DEFAULT_UDP_PORT


class LoginDialog(QDialog):
    def __init__(self, parent=None, default_username=""):
        super().__init__(parent)
        self.setWindowTitle("VimCord — Login & Registration")
        self.resize(480, 580)
        self.setMinimumSize(460, 560)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        # Set window icon from icon.ico
        self.icon_path = Path(__file__).resolve().parents[3] / "icon.ico"
        if self.icon_path.exists():
            self.setWindowIcon(QIcon(str(self.icon_path)))

        # Loaded config defaults from AppData
        saved_cfg = load_config()
        self.server_host = saved_cfg.get("host", "127.0.0.1")
        self.tcp_port = saved_cfg.get("tcp_port", DEFAULT_TCP_PORT)
        self.udp_port = saved_cfg.get("udp_port", DEFAULT_UDP_PORT)
        self.username = default_username or saved_cfg.get("username", "")
        self.password = saved_cfg.get("saved_password", "") if saved_cfg.get("auto_login") else ""
        self.auto_login = saved_cfg.get("auto_login", False)
        self.action = "login"  # "login" or "register"

        self._init_ui()

    def _save_current_config(self):
        save_config({
            "host": self.server_host,
            "tcp_port": self.tcp_port,
            "udp_port": self.udp_port,
            "username": self.username,
            "saved_password": self.password if self.auto_login else "",
            "auto_login": self.auto_login,
        })

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(28, 22, 28, 22)
        main_layout.setSpacing(14)

        # Header Title with icon.ico
        header_box = QWidget()
        h_layout = QHBoxLayout(header_box)
        h_layout.setContentsMargins(0, 0, 0, 0)
        h_layout.setSpacing(12)
        h_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        if self.icon_path.exists():
            icon_lbl = QLabel()
            pm = QPixmap(str(self.icon_path))
            if not pm.isNull():
                icon_lbl.setPixmap(pm.scaled(38, 38, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
                h_layout.addWidget(icon_lbl)

        title = QLabel("VimCord")
        title.setStyleSheet("font-size: 28px; font-weight: 800; color: #ffffff;")
        h_layout.addWidget(title)
        main_layout.addWidget(header_box)

        subtitle = QLabel("Log in to your account or create a new one")
        subtitle.setStyleSheet("color: #949ba4; font-size: 13px;")
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
                padding: 10px 30px;
                font-weight: bold;
                font-size: 13px;
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
        l_layout.setContentsMargins(20, 20, 20, 20)
        l_layout.setSpacing(10)

        lbl_u = QLabel("USERNAME:")
        lbl_u.setStyleSheet("color: #b5bac1; font-weight: bold; font-size: 11px;")
        l_layout.addWidget(lbl_u)

        self.login_user_input = QLineEdit()
        self.login_user_input.setPlaceholderText("e.g. Alex")
        self.login_user_input.setText(self.username)
        self.login_user_input.setStyleSheet("""
            QLineEdit {
                background-color: #1e1f22; color: #ffffff; border: 1px solid #383a40;
                border-radius: 6px; padding: 10px 12px; font-size: 14px;
            }
            QLineEdit:focus { border: 1px solid #5865F2; }
        """)
        l_layout.addWidget(self.login_user_input)

        lbl_p = QLabel("PASSWORD:")
        lbl_p.setStyleSheet("color: #b5bac1; font-weight: bold; font-size: 11px; margin-top: 4px;")
        l_layout.addWidget(lbl_p)

        self.login_pass_input = QLineEdit()
        self.login_pass_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.login_pass_input.setPlaceholderText("Enter your password...")
        self.login_pass_input.setText(self.password)
        self.login_pass_input.setStyleSheet("""
            QLineEdit {
                background-color: #1e1f22; color: #ffffff; border: 1px solid #383a40;
                border-radius: 6px; padding: 10px 12px; font-size: 14px;
            }
            QLineEdit:focus { border: 1px solid #5865F2; }
        """)
        self.login_pass_input.returnPressed.connect(self._on_login_click)
        l_layout.addWidget(self.login_pass_input)

        self.auto_login_cb = QCheckBox("Remember me & auto-login")
        self.auto_login_cb.setChecked(self.auto_login)
        self.auto_login_cb.setStyleSheet("""
            QCheckBox { color: #949ba4; font-size: 12px; margin-top: 4px; }
            QCheckBox::indicator { width: 16px; height: 16px; }
        """)
        l_layout.addWidget(self.auto_login_cb)

        l_btn = QPushButton("Log In")
        l_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        l_btn.setStyleSheet("""
            QPushButton {
                background-color: #5865F2; color: white; font-weight: bold;
                padding: 11px; border-radius: 6px; font-size: 15px; margin-top: 10px; border: none;
            }
            QPushButton:hover { background-color: #4752c4; }
        """)
        l_btn.clicked.connect(self._on_login_click)
        l_layout.addWidget(l_btn)
        l_layout.addStretch(1)

        self.tabs.addTab(tab_login, "Log In")

        # Tab 2: Register
        tab_reg = QWidget()
        r_layout = QVBoxLayout(tab_reg)
        r_layout.setContentsMargins(20, 20, 20, 20)
        r_layout.setSpacing(8)

        lbl_ru = QLabel("DESIRED USERNAME:")
        lbl_ru.setStyleSheet("color: #b5bac1; font-weight: bold; font-size: 11px;")
        r_layout.addWidget(lbl_ru)

        self.reg_user_input = QLineEdit()
        self.reg_user_input.setPlaceholderText("Choose a username...")
        self.reg_user_input.setStyleSheet("""
            QLineEdit {
                background-color: #1e1f22; color: #ffffff; border: 1px solid #383a40;
                border-radius: 6px; padding: 9px 12px; font-size: 14px;
            }
            QLineEdit:focus { border: 1px solid #23a55a; }
        """)
        r_layout.addWidget(self.reg_user_input)

        lbl_rp1 = QLabel("PASSWORD (min. 4 characters):")
        lbl_rp1.setStyleSheet("color: #b5bac1; font-weight: bold; font-size: 11px; margin-top: 2px;")
        r_layout.addWidget(lbl_rp1)

        self.reg_pass_input = QLineEdit()
        self.reg_pass_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.reg_pass_input.setPlaceholderText("Create a secure password...")
        self.reg_pass_input.setStyleSheet("""
            QLineEdit {
                background-color: #1e1f22; color: #ffffff; border: 1px solid #383a40;
                border-radius: 6px; padding: 9px 12px; font-size: 14px;
            }
            QLineEdit:focus { border: 1px solid #23a55a; }
        """)
        r_layout.addWidget(self.reg_pass_input)

        lbl_rp2 = QLabel("CONFIRM PASSWORD:")
        lbl_rp2.setStyleSheet("color: #b5bac1; font-weight: bold; font-size: 11px; margin-top: 2px;")
        r_layout.addWidget(lbl_rp2)

        self.reg_pass2_input = QLineEdit()
        self.reg_pass2_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.reg_pass2_input.setPlaceholderText("Repeat your password...")
        self.reg_pass2_input.setStyleSheet("""
            QLineEdit {
                background-color: #1e1f22; color: #ffffff; border: 1px solid #383a40;
                border-radius: 6px; padding: 9px 12px; font-size: 14px;
            }
            QLineEdit:focus { border: 1px solid #23a55a; }
        """)
        self.reg_pass2_input.returnPressed.connect(self._on_register_click)
        r_layout.addWidget(self.reg_pass2_input)

        r_btn = QPushButton("Create Account")
        r_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        r_btn.setStyleSheet("""
            QPushButton {
                background-color: #23a55a; color: white; font-weight: bold;
                padding: 11px; border-radius: 6px; font-size: 15px; margin-top: 8px; border: none;
            }
            QPushButton:hover { background-color: #1f9250; }
        """)
        r_btn.clicked.connect(self._on_register_click)
        r_layout.addWidget(r_btn)
        r_layout.addStretch(1)

        self.tabs.addTab(tab_reg, "Register")
        main_layout.addWidget(self.tabs, 1)

        # Server Settings Row (Host & Ports)
        srv_box = QWidget()
        srv_layout = QHBoxLayout(srv_box)
        srv_layout.setContentsMargins(0, 4, 0, 0)
        srv_layout.setSpacing(10)

        v_host = QVBoxLayout()
        v_host.setSpacing(4)
        lbl_sh = QLabel("SERVER ADDRESS:")
        lbl_sh.setStyleSheet("color: #80848e; font-size: 11px; font-weight: bold;")
        v_host.addWidget(lbl_sh)
        self.host_input = QLineEdit()
        self.host_input.setText(self.server_host)
        self.host_input.setStyleSheet("""
            QLineEdit {
                background-color: #1e1f22; color: #dbdee1; border: 1px solid #383a40;
                border-radius: 6px; padding: 6px 10px; font-size: 13px;
            }
        """)
        v_host.addWidget(self.host_input)
        srv_layout.addLayout(v_host, 2)

        v_port = QVBoxLayout()
        v_port.setSpacing(4)
        lbl_sp = QLabel("PORT:")
        lbl_sp.setStyleSheet("color: #80848e; font-size: 11px; font-weight: bold;")
        v_port.addWidget(lbl_sp)
        self.port_input = QSpinBox()
        self.port_input.setRange(1024, 65535)
        self.port_input.setValue(self.tcp_port)
        self.port_input.setStyleSheet("""
            QSpinBox {
                background-color: #1e1f22; color: #dbdee1; border: 1px solid #383a40;
                border-radius: 6px; padding: 6px 10px; font-size: 13px;
            }
        """)
        v_port.addWidget(self.port_input)
        srv_layout.addLayout(v_port, 1)

        main_layout.addWidget(srv_box)

    def _on_login_click(self):
        uname = self.login_user_input.text().strip()
        passwd = self.login_pass_input.text().strip()
        host = self.host_input.text().strip()

        if not uname:
            QMessageBox.warning(self, "Validation Error", "Please enter your username!")
            self.login_user_input.setFocus()
            return
        if not passwd:
            QMessageBox.warning(self, "Validation Error", "Please enter your password!")
            self.login_pass_input.setFocus()
            return
        if not host:
            QMessageBox.warning(self, "Validation Error", "Please enter server address!")
            self.host_input.setFocus()
            return

        self.action = "login"
        self.username = uname
        self.password = passwd
        self.server_host = host
        self.tcp_port = self.port_input.value()
        self.udp_port = self.tcp_port + 1
        self.auto_login = self.auto_login_cb.isChecked()
        self._save_current_config()
        self.accept()

    def _on_register_click(self):
        uname = self.reg_user_input.text().strip()
        p1 = self.reg_pass_input.text().strip()
        p2 = self.reg_pass2_input.text().strip()
        host = self.host_input.text().strip()

        if not uname or len(uname) < 2:
            QMessageBox.warning(self, "Validation Error", "Username must be at least 2 characters!")
            self.reg_user_input.setFocus()
            return
        if not p1 or len(p1) < 4:
            QMessageBox.warning(self, "Validation Error", "Password must be at least 4 characters!")
            self.reg_pass_input.setFocus()
            return
        if p1 != p2:
            QMessageBox.warning(self, "Validation Error", "Passwords do not match!")
            self.reg_pass2_input.setFocus()
            return
        if not host:
            QMessageBox.warning(self, "Validation Error", "Please enter server address!")
            self.host_input.setFocus()
            return

        self.action = "register"
        self.username = uname
        self.password = p1
        self.server_host = host
        self.tcp_port = self.port_input.value()
        self.udp_port = self.tcp_port + 1
        self.auto_login = True
        self._save_current_config()
        self.accept()
