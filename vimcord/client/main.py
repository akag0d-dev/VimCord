"""
Main entry point for VimCord Client application.
Supports registration, authentication, persistent session initialization,
AppData auto-login, audio setup, and clean retry handling.
"""

import argparse
import sys
from pathlib import Path
from PyQt6.QtCore import QEventLoop, QTimer
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QMessageBox

from vimcord.client.audio.audio_manager import AudioManager
from vimcord.client.config import load_config, save_config
from vimcord.client.network.tcp_client import TCPClient
from vimcord.client.network.udp_voice import UDPVoiceClient
from vimcord.client.ui.login_dialog import LoginDialog
from vimcord.client.ui.main_window import MainWindow
from vimcord.client.ui.styles import DARK_THEME_QSS
from vimcord.common.protocol import DEFAULT_TCP_PORT, DEFAULT_UDP_PORT


def main():
    parser = argparse.ArgumentParser(description="VimCord Client")
    parser.add_argument("--user", default="", help="Pre-filled username")
    parser.add_argument("--host", default="", help="Server IP address")
    parser.add_argument("--tcp-port", type=int, default=0, help="Server TCP port")
    parser.add_argument("--udp-port", type=int, default=0, help="Server UDP port")
    parser.add_argument("--auto", action="store_true", help="Auto-connect without login dialog")
    parser.add_argument("--no-auto-login", action="store_true", help="Disable AppData auto-login")
    args = parser.parse_args()

    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("akag0d.vimcord.desktop.client")
        except Exception:
            pass

    app = QApplication(sys.argv)
    app.setStyleSheet(DARK_THEME_QSS)

    icon_path = Path(__file__).resolve().parents[2] / "icon.ico"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    saved_cfg = load_config()
    server_host = args.host or saved_cfg.get("host", "127.0.0.1")
    tcp_port = args.tcp_port or saved_cfg.get("tcp_port", DEFAULT_TCP_PORT)
    udp_port = args.udp_port or saved_cfg.get("udp_port", DEFAULT_UDP_PORT)
    username = args.user or saved_cfg.get("username", "")
    password = saved_cfg.get("saved_password", "") if (saved_cfg.get("auto_login") and not args.no_auto_login) else ""
    action = "login"

    # Audio & network subsystems
    audio_mgr = AudioManager()
    tcp_client = TCPClient()
    udp_voice = UDPVoiceClient(audio_mgr)

    authenticated = False
    login_data = {}

    # Attempt automatic background login if enabled in AppData
    if (saved_cfg.get("auto_login") and not args.no_auto_login and username and password and not args.auto):
        if tcp_client.connect_to_server(server_host, tcp_port):
            auto_res = {"success": False, "data": {}}
            loop_auto = QEventLoop()

            def on_auto_login(ok, data):
                auto_res["success"] = ok
                auto_res["data"] = data
                loop_auto.quit()

            tcp_client.signals.login_response.connect(on_auto_login)
            try:
                tcp_client.send_login(username, password)
                QTimer.singleShot(2500, loop_auto.quit)
                loop_auto.exec()
            finally:
                try:
                    tcp_client.signals.login_response.disconnect(on_auto_login)
                except Exception:
                    pass

            if auto_res["success"]:
                authenticated = True
                login_data = auto_res["data"]
            else:
                tcp_client.disconnect()

    # Interactive login loop
    while not authenticated:
        if not args.auto or not username:
            login_dlg = LoginDialog(default_username=username)
            if login_dlg.exec() != LoginDialog.DialogCode.Accepted:
                sys.exit(0)

            server_host = login_dlg.server_host
            tcp_port = login_dlg.tcp_port
            udp_port = login_dlg.udp_port
            username = login_dlg.username
            password = login_dlg.password
            action = login_dlg.action

        # Ensure TCP connection is active
        if not tcp_client.sock or not tcp_client._is_running:
            tcp_client.disconnect()
            if not tcp_client.connect_to_server(server_host, tcp_port):
                QMessageBox.critical(
                    None,
                    "Connection Error",
                    f"Could not connect to {server_host}:{tcp_port}!\nPlease ensure the server is running."
                )
                if args.auto:
                    sys.exit(1)
                continue

        # Handle Registration if requested
        if action == "register":
            reg_result = {"success": False, "message": ""}
            loop_reg = QEventLoop()

            def on_reg(ok, msg):
                reg_result["success"] = ok
                reg_result["message"] = msg
                loop_reg.quit()

            tcp_client.signals.register_response.connect(on_reg)
            try:
                tcp_client.send_register(username, password)
                QTimer.singleShot(4000, loop_reg.quit)
                loop_reg.exec()
            finally:
                try:
                    tcp_client.signals.register_response.disconnect(on_reg)
                except Exception:
                    pass

            if not reg_result["success"]:
                QMessageBox.warning(None, "Registration Error", reg_result.get("message", "Registration failed."))
                if args.auto:
                    sys.exit(1)
                continue
            else:
                QMessageBox.information(None, "Success", "Account created successfully! Logging in...")

        # Handle Login
        login_res = {"success": False, "data": {}, "message": ""}
        loop_login = QEventLoop()

        def on_login(ok, data):
            login_res["success"] = ok
            login_res["data"] = data
            login_res["message"] = data.get("message", "")
            loop_login.quit()

        tcp_client.signals.login_response.connect(on_login)
        try:
            tcp_client.send_login(username, password)
            QTimer.singleShot(4000, loop_login.quit)
            loop_login.exec()
        finally:
            try:
                tcp_client.signals.login_response.disconnect(on_login)
            except Exception:
                pass

        if login_res["success"]:
            authenticated = True
            login_data = login_res["data"]
        else:
            err_msg = login_res["message"] or "Invalid username or password, or server is unreachable."
            QMessageBox.warning(None, "Login Error", err_msg)
            # Do NOT exit, loop back smoothly to let user retry immediately without restart
            if args.auto:
                sys.exit(1)

    user_id = login_data.get("user_id", "")
    logged_in_name = login_data.get("username", username)
    avatar_color = login_data.get("avatar_color", "#5865F2")
    avatar_image = login_data.get("avatar_image", "")
    bio = login_data.get("bio", "")
    status_text = login_data.get("status_text", "Online")
    if status_text == "В сети":
        status_text = "Online"
    display_name = login_data.get("display_name") or logged_in_name
    banner_color = login_data.get("banner_color", "#5865F2")
    banner_image = login_data.get("banner_image", "")
    rooms = login_data.get("rooms", [])
    users = login_data.get("users", [])
    friends = login_data.get("friends", [])

    # Open main window
    main_win = MainWindow(tcp_client, audio_mgr, udp_voice)
    main_win.initialize_session(
        user_id=user_id,
        username=logged_in_name,
        avatar_color=avatar_color,
        status_text=status_text,
        rooms=rooms,
        users=users,
        friends=friends,
        host=server_host,
        udp_port=udp_port,
        avatar_image=avatar_image,
        bio=bio,
        display_name=display_name,
        banner_color=banner_color,
        banner_image=banner_image
    )
    main_win.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
