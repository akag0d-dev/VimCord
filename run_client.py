#!/usr/bin/env python3
"""
Launcher script for VimCord Client.
Automatically launches the high-performance Rust + Tauri client binary if compiled,
or falls back to the Python pywebview client.
"""
import sys
import os
import subprocess
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent

def main():
    # Check for Rust Tauri binary
    tauri_bin = ROOT_DIR / "src-tauri" / "target" / "debug" / "vimcord.exe"
    tauri_release = ROOT_DIR / "src-tauri" / "target" / "release" / "vimcord.exe"

    target_exe = None
    if tauri_release.exists():
        target_exe = tauri_release
    elif tauri_bin.exists():
        target_exe = tauri_bin

    # If --python flag is passed or binary not found, run python client
    if "--python" not in sys.argv and target_exe and target_exe.exists():
        sys.exit(subprocess.call([str(target_exe)] + sys.argv[1:]))

    # Python client fallback
    sys.path.insert(0, str(ROOT_DIR))
    from vimcord.client.main import main as py_main
    py_main()

if __name__ == "__main__":
    main()
