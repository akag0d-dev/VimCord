"""
Main entry point for VimCord Client application.
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

    # If not auto-connect or username is empty, prompt login dialog
    if not args.auto or not username:
        login_dlg = LoginDialog(default_username=username)
        if login_dlg.exec() != LoginDialog.DialogCode.Accepted:
            sys.exit(0)

        server_host = login_dlg.server_host
        tcp_port = login_dlg.tcp_port
        udp_port = login_dlg.udp_port
        username = login_dlg.username

    # Initialize audio & network subsystems
    audio_mgr = AudioManager()
    tcp_client = TCPClient()
    udp_voice = UDPVoiceClient(audio_mgr)

    # Connect to TCP server
    if not tcp_client.connect_to_server(server_host, tcp_port):
        QMessageBox.critical(None, "Ошибка", f"Не удалось подключиться к серверу {server_host}:{tcp_port}!\nУбедитесь, что run_server.py запущен.")
        sys.exit(1)

    # Wait for login response synchronously via local event loop
    login_result = {"success": False, "data": {}}
    loop = QEventLoop()

    def on_login_resp(success, data):
        login_result["success"] = success
        login_result["data"] = data
        loop.quit()

    def on_login_timeout():
        loop.quit()

    tcp_client.signals.login_response.connect(on_login_resp)
    tcp_client.send_login(username)

    # 4 second timeout for login
    QTimer.singleShot(4000, on_login_timeout)
    loop.exec()

    if not login_result["success"]:
        QMessageBox.critical(None, "Ошибка", "Сервер не ответил на запрос входа или отклонил его.")
        tcp_client.disconnect()
        sys.exit(1)

    data = login_result["data"]
    user_id = data.get("user_id", "")
    logged_in_name = data.get("username", username)
    rooms = data.get("rooms", [])
    users = data.get("users", [])

    # Open main window
    main_win = MainWindow(tcp_client, audio_mgr, udp_voice)
    main_win.initialize_session(
        user_id=user_id,
        username=logged_in_name,
        rooms=rooms,
        users=users,
        host=server_host,
        udp_port=udp_port
    )
    main_win.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
