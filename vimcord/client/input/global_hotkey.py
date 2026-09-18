"""
Global Keyboard and Mouse Hook Manager for Push-to-Talk and keybinds.
Works globally across Windows regardless of active window or full-screen games,
and normalizes virtual key codes (VK) so keyboard layouts (EN, RU, etc.) do not affect PTT.
"""

import logging
import threading
from typing import Optional, Callable
from pynput import keyboard, mouse

logger = logging.getLogger("VimCord.GlobalHotkey")

# Map standard key names to virtual key codes (Windows)
SPECIAL_VK = {
    "SPACE": 32,
    "CTRL": 17,
    "CONTROL": 17,
    "LCTRL": 162,
    "RCTRL": 163,
    "SHIFT": 16,
    "LSHIFT": 160,
    "RSHIFT": 161,
    "ALT": 18,
    "LALT": 164,
    "RALT": 165,
    "CAPS": 20,
    "CAPSLOCK": 20,
    "CAPS LOCK": 20,
    "TAB": 9,
    "RETURN": 13,
    "ENTER": 13,
    "ESCAPE": 27,
    "ESC": 27,
    "BACKSPACE": 8,
    "F1": 112, "F2": 113, "F3": 114, "F4": 115, "F5": 116, "F6": 117,
    "F7": 118, "F8": 119, "F9": 120, "F10": 121, "F11": 122, "F12": 123
}

MOUSE_BUTTON_NAMES = {
    mouse.Button.middle: "Mouse 3",
    mouse.Button.x1: "Mouse 4",
    mouse.Button.x2: "Mouse 5",
    mouse.Button.left: "Mouse 1",
    mouse.Button.right: "Mouse 2"
}

NAME_TO_MOUSE_BUTTON = {
    "MOUSE 1": mouse.Button.left,
    "MOUSE 2": mouse.Button.right,
    "MOUSE 3": mouse.Button.middle,
    "MOUSE 4": mouse.Button.x1,
    "MOUSE 5": mouse.Button.x2,
}


def normalize_key_str(raw: str) -> str:
    s = raw.strip()
    u = s.upper()
    if u in ("MOUSE 1", "MOUSE 2", "MOUSE 3", "MOUSE 4", "MOUSE 5"):
        return u.title()
    if u in ("SPACE", "SPACEBAR"):
        return "Space"
    if u in ("CTRL", "CONTROL"):
        return "Ctrl"
    if u in ("SHIFT",):
        return "Shift"
    if u in ("ALT",):
        return "Alt"
    if u in ("CAPS", "CAPSLOCK", "CAPS LOCK"):
        return "Caps Lock"
    if len(s) == 1:
        return s.upper()
    return s.title()


class GlobalHotkeyManager:
    def __init__(self, on_ptt_state_changed: Optional[Callable[[bool], None]] = None):
        self.on_ptt_state_changed = on_ptt_state_changed
        self.ptt_mode: bool = False
        self.ptt_key: str = "Space"
        self._is_key_down: bool = False
        self._recording: bool = False
        self._record_callback: Optional[Callable[[str], None]] = None

        self._kb_listener: Optional[keyboard.Listener] = None
        self._mouse_listener: Optional[mouse.Listener] = None
        self._lock = threading.Lock()

    def start(self):
        """Starts background global keyboard and mouse listeners."""
        try:
            self._kb_listener = keyboard.Listener(
                on_press=self._on_key_press,
                on_release=self._on_key_release
            )
            self._kb_listener.daemon = True
            self._kb_listener.start()

            self._mouse_listener = mouse.Listener(
                on_click=self._on_mouse_click
            )
            self._mouse_listener.daemon = True
            self._mouse_listener.start()
            logger.info("Global hotkey listeners started")
        except Exception as e:
            logger.error(f"Failed to start global hotkey listeners: {e}")

    def stop(self):
        """Stops global listeners."""
        if self._kb_listener:
            try:
                self._kb_listener.stop()
            except Exception:
                pass
            self._kb_listener = None
        if self._mouse_listener:
            try:
                self._mouse_listener.stop()
            except Exception:
                pass
            self._mouse_listener = None

    def set_ptt_config(self, enabled: bool, hotkey: str):
        with self._lock:
            self.ptt_mode = enabled
            self.ptt_key = normalize_key_str(hotkey or "Space")
            if not enabled and self._is_key_down:
                self._is_key_down = False
                if self.on_ptt_state_changed:
                    self.on_ptt_state_changed(False)

    def start_recording(self, callback: Callable[[str], None]):
        """Enter recording mode to capture the next pressed key or mouse button."""
        with self._lock:
            self._recording = True
            self._record_callback = callback

    def stop_recording(self):
        with self._lock:
            self._recording = False
            self._record_callback = None

    def _get_key_vk(self, key) -> Optional[int]:
        if hasattr(key, 'vk') and key.vk is not None:
            return key.vk
        if hasattr(key, 'value') and hasattr(key.value, 'vk'):
            return key.value.vk
        return None

    def _format_key_name(self, key) -> str:
        # Check special enum keys
        if isinstance(key, keyboard.Key):
            name = key.name.upper()
            if name == "SPACE":
                return "Space"
            if "CTRL" in name:
                return "Ctrl"
            if "SHIFT" in name:
                return "Shift"
            if "ALT" in name:
                return "Alt"
            if name == "CAPS_LOCK":
                return "Caps Lock"
            if name == "TAB":
                return "Tab"
            if name == "ENTER":
                return "Enter"
            return key.name.title()
        
        # Character key
        vk = self._get_key_vk(key)
        if vk is not None:
            if 65 <= vk <= 90:
                return chr(vk) # Standard A-Z
            if 48 <= vk <= 57:
                return chr(vk) # Standard 0-9
            if 112 <= vk <= 123:
                return f"F{vk - 111}"

        if hasattr(key, 'char') and key.char:
            return key.char.upper()

        return str(key).replace("Key.", "").title()

    def _matches_target_key(self, key) -> bool:
        target = self.ptt_key.upper()
        if target.startswith("MOUSE"):
            return False

        vk = self._get_key_vk(key)

        # Check special key vk
        target_vk = SPECIAL_VK.get(target)
        if target_vk is not None:
            if vk == target_vk:
                return True
            # Check Ctrl/Shift/Alt variants
            if target in ("CTRL", "CONTROL") and vk in (17, 162, 163):
                return True
            if target == "SHIFT" and vk in (16, 160, 161):
                return True
            if target == "ALT" and vk in (18, 164, 165):
                return True

        # Check standard single character A-Z / 0-9 by VK
        if len(target) == 1 and vk is not None:
            target_ord = ord(target)
            if vk == target_ord:
                return True

        # Fallback check by name
        formatted = self._format_key_name(key).upper()
        return formatted == target

    def _on_key_press(self, key):
        if self._recording:
            with self._lock:
                if self._recording and self._record_callback:
                    name = self._format_key_name(key)
                    cb = self._record_callback
                    self._recording = False
                    self._record_callback = None
                    cb(name)
            return

        if not self.ptt_mode:
            return

        if self._matches_target_key(key):
            if not self._is_key_down:
                self._is_key_down = True
                if self.on_ptt_state_changed:
                    self.on_ptt_state_changed(True)

    def _on_key_release(self, key):
        if self._recording:
            return

        if not self.ptt_mode:
            return

        if self._matches_target_key(key):
            if self._is_key_down:
                self._is_key_down = False
                if self.on_ptt_state_changed:
                    self.on_ptt_state_changed(False)

    def _on_mouse_click(self, x, y, button, pressed):
        btn_name = MOUSE_BUTTON_NAMES.get(button)
        if not btn_name:
            return

        if self._recording and pressed:
            with self._lock:
                if self._recording and self._record_callback:
                    cb = self._record_callback
                    self._recording = False
                    self._record_callback = None
                    cb(btn_name)
            return

        if not self.ptt_mode:
            return

        target_btn = NAME_TO_MOUSE_BUTTON.get(self.ptt_key.upper())
        if target_btn and button == target_btn:
            if pressed and not self._is_key_down:
                self._is_key_down = True
                if self.on_ptt_state_changed:
                    self.on_ptt_state_changed(True)
            elif not pressed and self._is_key_down:
                self._is_key_down = False
                if self.on_ptt_state_changed:
                    self.on_ptt_state_changed(False)
