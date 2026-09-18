"""
System Tray Manager using pystray for VimCord.
Supports dynamic localization (EN / RU) based on client settings,
speaking indicator badge on the tray icon, and background running.
"""

import logging
import os
import threading
from typing import Optional, Callable
from PIL import Image, ImageDraw
import pystray
from pystray import MenuItem as item, Menu

from vimcord.client.config import get_resource_path
from vimcord.client.i18n import t

logger = logging.getLogger("VimCord.Tray")


class TrayManager:
    def __init__(self, on_open: Optional[Callable[[], None]] = None, on_quit: Optional[Callable[[], None]] = None):
        self.on_open = on_open
        self.on_quit = on_quit
        self.icon: Optional[pystray.Icon] = None
        self._thread: Optional[threading.Thread] = None
        self._is_speaking: bool = False
        self._base_image: Optional[Image.Image] = None

    def _load_base_image(self) -> Image.Image:
        if self._base_image is not None:
            return self._base_image

        icon_path = get_resource_path("icon.ico")
        if os.path.exists(icon_path):
            try:
                with Image.open(icon_path) as img:
                    self._base_image = img.convert("RGBA").resize((64, 64), Image.Resampling.LANCZOS)
                return self._base_image
            except Exception as e:
                logger.debug(f"Failed to open icon.ico: {e}")

        # Fallback generated icon
        img = Image.new("RGBA", (64, 64), color=(88, 101, 242, 255))
        draw = ImageDraw.Draw(img)
        draw.ellipse((8, 8, 56, 56), fill=(43, 45, 49, 255))
        self._base_image = img
        return self._base_image

    def _create_icon_image(self, is_speaking: bool = False) -> Image.Image:
        base = self._load_base_image().copy()
        if is_speaking:
            draw = ImageDraw.Draw(base)
            # Draw bright green circle at bottom-right
            draw.ellipse((42, 42, 62, 62), fill=(35, 165, 90, 255), outline=(0, 0, 0, 255), width=2)
        return base

    def _build_menu(self) -> Menu:
        open_label = t("tray_open", "Open VimCord")
        quit_label = t("tray_quit", "Quit VimCord")

        def handle_open(icon, item):
            if self.on_open:
                self.on_open()

        def handle_quit(icon, item):
            self.stop()
            if self.on_quit:
                self.on_quit()

        return Menu(
            item(open_label, handle_open, default=True),
            Menu.SEPARATOR,
            item(quit_label, handle_quit)
        )

    def start(self):
        """Starts the system tray icon in a dedicated background thread."""
        try:
            image = self._create_icon_image(False)
            menu = self._build_menu()
            self.icon = pystray.Icon("VimCord", image, "VimCord", menu)

            self._thread = threading.Thread(target=self.icon.run, daemon=True)
            self._thread.start()
            logger.info("System tray icon started")
        except Exception as e:
            logger.error(f"Failed to start system tray: {e}")

    def update_language(self):
        """Rebuilds the context menu to reflect the selected language (EN / RU)."""
        if self.icon:
            try:
                self.icon.menu = self._build_menu()
            except Exception as e:
                logger.debug(f"Failed to update tray menu: {e}")

    def update_speaking(self, is_speaking: bool):
        """Updates tray icon badge when voice activity changes."""
        if self.icon and is_speaking != self._is_speaking:
            self._is_speaking = is_speaking
            try:
                self.icon.icon = self._create_icon_image(is_speaking)
            except Exception as e:
                logger.debug(f"Failed to update tray icon: {e}")

    def stop(self):
        """Stops and removes the tray icon."""
        if self.icon:
            try:
                self.icon.stop()
            except Exception:
                pass
            self.icon = None
