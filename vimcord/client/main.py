"""
Main entry point for VimCord Client application (pywebview).
Supports automatic login, custom titlebar, persistent AppData settings,
audio subsystems, global Push-to-Talk, and system tray.
"""

import argparse
import logging
import os
import sys
from pathlib import Path
import webview

from vimcord.client.api import VimCordAPI
from vimcord.client.config import load_config, get_resource_path
from vimcord.common.protocol import DEFAULT_TCP_PORT, DEFAULT_UDP_PORT

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("VimCord.Main")


def main():
    parser = argparse.ArgumentParser(description="VimCord Client")
    parser.add_argument("--user", default="", help="Pre-filled username")
    parser.add_argument("--host", default="", help="Server IP address")
    parser.add_argument("--tcp-port", type=int, default=0, help="Server TCP port")
    parser.add_argument("--udp-port", type=int, default=0, help="Server UDP port")
    parser.add_argument("--auto", action="store_true", help="Auto-connect without login dialog")
    parser.add_argument("--no-auto-login", action="store_true", help="Disable AppData auto-login")
    parser.add_argument("--debug", action="store_true", help="Enable WebView Developer Tools")
    args = parser.parse_args()

    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("akag0d.vimcord.desktop.client")
        except Exception:
            pass

    api = VimCordAPI()

    web_index = get_resource_path("vimcord/client/web/index.html")
    if not web_index.exists():
        web_index = Path(__file__).resolve().parent / "web" / "index.html"

    icon_path = get_resource_path("icon.ico")
    if not icon_path.exists():
        icon_path = Path(__file__).resolve().parents[2] / "icon.ico"

    window = webview.create_window(
        title="VimCord",
        url=str(web_index),
        js_api=api,
        width=460,
        height=620,
        min_size=(400, 500),
        background_color="#1e1f22",
        zoomable=False
    )
    api.set_window(window)

    def on_closing():
        api._tray.update_speaking(False)

    window.events.closing += on_closing

    # Start pywebview mainloop with native app icon
    webview.start(debug=args.debug, icon=str(icon_path) if icon_path.exists() else None)


if __name__ == "__main__":
    main()
