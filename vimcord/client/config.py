"""
Configuration and AppData storage manager for VimCord Client.
Persists server connection details, user credentials, auto-login state,
language, and theme in standard OS AppData directory.
"""

import json
import os
import sys
from pathlib import Path
from typing import Dict, Any, Optional

from vimcord.common.protocol import DEFAULT_TCP_PORT, DEFAULT_UDP_PORT

LEGACY_CONFIG_FILE = Path.home() / ".vimcord_client.json"


def get_appdata_dir() -> Path:
    """Returns the dedicated VimCord AppData directory."""
    if sys.platform == "win32":
        app_data = os.environ.get("APPDATA")
        if app_data:
            base_dir = Path(app_data)
        else:
            base_dir = Path.home() / "AppData" / "Roaming"
        target = base_dir / "VimCord"
    else:
        target = Path.home() / ".config" / "VimCord"

    target.mkdir(parents=True, exist_ok=True)
    return target


def get_config_file() -> Path:
    return get_appdata_dir() / "config.json"


DEFAULT_CONFIG: Dict[str, Any] = {
    "host": "194.226.123.199",
    "tcp_port": DEFAULT_TCP_PORT,
    "udp_port": DEFAULT_UDP_PORT,
    "username": "",
    "saved_password": "",
    "auto_login": False,
    "language": "en",
    "theme": "dark",
    "dnd_mode": False,
    "ptt_key": "Space",
    "stream_volume": 100,
    "call_volume": 100,
    "stream_resolution": "720p",
    "stream_fps": 15,
    "stream_quality": 45,
}


def load_config(config_file: Optional[Path] = None, config_path: Optional[Path] = None) -> Dict[str, Any]:
    """Loads client configuration, migrating legacy ~/.vimcord_client.json if needed."""
    cfg = dict(DEFAULT_CONFIG)
    target_file = config_path or config_file or get_config_file()

    # Check for legacy file migration if default path
    if config_file is None and config_path is None and not target_file.exists() and LEGACY_CONFIG_FILE.exists():
        try:
            with open(LEGACY_CONFIG_FILE, "r", encoding="utf-8") as f:
                legacy_data = json.load(f)
                cfg.update(legacy_data)
                if "language" not in legacy_data:
                    cfg["language"] = "en"
                save_config(cfg)
                return cfg
        except Exception:
            pass

    if target_file.exists():
        try:
            with open(target_file, "r", encoding="utf-8") as f:
                saved = json.load(f)
                cfg.update(saved)
        except Exception:
            pass

    return cfg


def save_config(cfg_updates: Dict[str, Any], config_file: Optional[Path] = None, config_path: Optional[Path] = None):
    """Saves updated client configuration to AppData config.json."""
    current = load_config(config_file=config_file, config_path=config_path)
    current.update(cfg_updates)
    target_file = config_path or config_file or get_config_file()
    try:
        with open(target_file, "w", encoding="utf-8") as f:
            json.dump(current, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def clear_auto_login(config_file: Optional[Path] = None, config_path: Optional[Path] = None):
    """Clears saved auto-login credentials while preserving username and other settings."""
    save_config({"auto_login": False, "saved_password": ""}, config_file=config_file, config_path=config_path)


# Convenience aliases
load_client_config = load_config
save_client_config = save_config
