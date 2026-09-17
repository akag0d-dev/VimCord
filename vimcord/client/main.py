"""
Main entry point for VimCord Client application.
Supports registration, authentication, persistent session initialization, and audio setup.
"""

import argparse
import sys
from PyQt6.QtCore import QEventLoop, QTimer
from PyQt6.QtWidgets import QApplication, QMessageBox

from vimcord.client.audio.audio_manager import AudioManager
from vimcord.client.network.tcp_client import TCPClient
from vimcord.client.network.udp_voice import UDPVoiceClient
from vimcord.client.ui.login_dialog import LoginDialog
from vimcord.client.ui.main_window import MainWindow
from vimcord.client.ui.styles import DARK_THEME_QSS
from vimcord.common.protocol import DEFAULT_TCP_PORT, DEFAULT_UDP_PORT


def main():
    parser = argparse.ArgumentParser(description="VimCord Client")
    parser.add_argument("--user", default="", help="Pre-filled username")
    parser.add_argument("--host", default="127.0.0.1", help="Server IP address")
    parser.add_argument("--tcp-port", type=int, default=DEFAULT_TCP_PORT, help="Server TCP port")
    parser.add_argument("--udp-port", type=int, default=DEFAULT_UDP_PORT, help="Server UDP port")
    parser.add_argument("--auto", action="store_true", help="Auto-connect without login dialog")
    args = parser.parse_args()

    app = QApplication(sys.argv)
    app.setStyleSheet(DARK_THEME_QSS)

    server_host = args.host
    tcp_port = args.tcp_port
    udp_port = args.udp_port
    username = args.user
    password = ""
    action = "login"

    # Audio & network subsystems
    audio_mgr = AudioManager()
    tcp_client = TCPClient()
    udp_voice = UDPVoiceClient(audio_mgr)

    authenticated = False
    login_data = {}

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

        # Connect if not connected
        if not tcp_client.sock:
            if not tcp_client.connect_to_server(server_host, tcp_port):
                QMessageBox.critical(None, "Ошибка подключения", f"Не удалось подключиться к {server_host}:{tcp_port}!\nУбедитесь, что run_server.py запущен.")
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
            tcp_client.send_register(username, password)
            QTimer.singleShot(4000, loop_reg.quit)
            loop_reg.exec()

            if not reg_result["success"]:
                QMessageBox.warning(None, "Ошибка регистрации", reg_result.get("message", "Не удалось зарегистрироваться"))
                if args.auto:
                    sys.exit(1)
                continue
            else:
                QMessageBox.information(None, "Успешно", "Аккаунт успешно создан! Выполняется автоматический вход...")

        # Handle Login
        login_res = {"success": False, "data": {}, "message": ""}
        loop_login = QEventLoop()

        def on_login(ok, data):
            login_res["success"] = ok
            login_res["data"] = data
            login_res["message"] = data.get("message", "")
            loop_login.quit()

        tcp_client.signals.login_response.connect(on_login)
        tcp_client.send_login(username, password)
        QTimer.singleShot(4000, loop_login.quit)
        loop_login.exec()

        if login_res["success"]:
            authenticated = True
            login_data = login_res["data"]
        else:
            err_msg = login_res["message"] or "Неверный логин/пароль или сервер недоступен."
            QMessageBox.warning(None, "Ошибка входа", err_msg)
            if args.auto:
                sys.exit(1)

    user_id = login_data.get("user_id", "")
    logged_in_name = login_data.get("username", username)
    avatar_color = login_data.get("avatar_color", "#5865F2")
    status_text = login_data.get("status_text", "В сети")
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
        udp_port=udp_port
    )
    main_win.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
