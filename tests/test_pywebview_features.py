"""
Unit tests for pywebview client architecture, global hotkeys,
dynamic tray localization, and clipboard / file utilities.
"""

import unittest
from unittest.mock import MagicMock
from vimcord.client.signals import Signal
from vimcord.client.input.global_hotkey import normalize_key_str, GlobalHotkeyManager
from vimcord.client.tray.tray_manager import TrayManager
from vimcord.client.i18n import set_language, get_language, t
from vimcord.client.api import VimCordAPI


class TestSignalEmitter(unittest.TestCase):
    def test_connect_emit_disconnect(self):
        sig = Signal(str, int)
        received = []

        def slot(text, num):
            received.append((text, num))

        sig.connect(slot)
        sig.emit("hello", 42)
        self.assertEqual(received, [("hello", 42)])

        sig.disconnect(slot)
        sig.emit("world", 100)
        self.assertEqual(len(received), 1)

    def test_emit_multiple_slots(self):
        sig = Signal()
        calls = []

        sig.connect(lambda: calls.append("a"))
        sig.connect(lambda: calls.append("b"))
        sig.emit()
        self.assertEqual(calls, ["a", "b"])


class TestGlobalHotkeyManager(unittest.TestCase):
    def test_normalize_key_strings(self):
        self.assertEqual(normalize_key_str("space"), "Space")
        self.assertEqual(normalize_key_str("ctrl"), "Ctrl")
        self.assertEqual(normalize_key_str("shift"), "Shift")
        self.assertEqual(normalize_key_str("caps"), "Caps Lock")
        self.assertEqual(normalize_key_str("capslock"), "Caps Lock")
        self.assertEqual(normalize_key_str("v"), "V")
        self.assertEqual(normalize_key_str("f5"), "F5")
        self.assertEqual(normalize_key_str("mouse 3"), "Mouse 3")
        self.assertEqual(normalize_key_str("mouse 4"), "Mouse 4")
        self.assertEqual(normalize_key_str("mouse 5"), "Mouse 5")

    def test_hotkey_configuration(self):
        callback = MagicMock()
        mgr = GlobalHotkeyManager(on_ptt_state_changed=callback)
        mgr.set_ptt_config(True, "Mouse 5")
        self.assertTrue(mgr.ptt_mode)
        self.assertEqual(mgr.ptt_key, "Mouse 5")

        mgr.set_ptt_config(False, "Space")
        self.assertFalse(mgr.ptt_mode)
        self.assertEqual(mgr.ptt_key, "Space")


class TestTrayLocalization(unittest.TestCase):
    def test_dynamic_tray_menu_translations(self):
        tm = TrayManager()

        # English
        set_language("en")
        self.assertEqual(get_language(), "en")
        menu_en = tm._build_menu()
        menu_items_en = [item.text for item in menu_en.items if hasattr(item, "text")]
        self.assertIn("Open VimCord", menu_items_en)
        self.assertIn("Quit VimCord", menu_items_en)

        # Russian
        set_language("ru")
        self.assertEqual(get_language(), "ru")
        menu_ru = tm._build_menu()
        menu_items_ru = [item.text for item in menu_ru.items if hasattr(item, "text")]
        self.assertIn("Открыть VimCord", menu_items_ru)
        self.assertIn("Полностью выйти", menu_items_ru)

        # Reset back
        set_language("en")


class TestVimCordAPIBridge(unittest.TestCase):
    def test_initial_state_loading(self):
        api = VimCordAPI()
        state = api.get_initial_state()
        self.assertIn("config", state)
        self.assertIn("language", state)
        self.assertIn("audio_devices", state)
        self.assertIn("theme", state)
        self.assertIn("ptt_key", state)
        api._hotkey_mgr.stop()
        api._tray.stop()

    def test_ptt_config_update(self):
        api = VimCordAPI()
        api.set_ptt_config(True, "Mouse 4")
        self.assertTrue(api._audio_manager.ptt_mode)
        self.assertEqual(api._hotkey_mgr.ptt_key, "Mouse 4")
        api._hotkey_mgr.stop()
        api._tray.stop()


if __name__ == "__main__":
    unittest.main()
