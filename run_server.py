#!/usr/bin/env python3
"""
Launcher script for VimCord Server.
Automatically detects and launches the compiled Rust server if available,
or seamlessly falls back to the Python server.

Usage: python run_server.py [--host 0.0.0.0] [--tcp-port 9988] [--udp-port 9989]
"""
import sys
import os
import subprocess

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

def find_rust_binary():
    exe_suffix = ".exe" if sys.platform == "win32" else ""
    candidates = [
        os.path.join(PROJECT_ROOT, "server-rust", "target", "release", f"vimcord-server{exe_suffix}"),
        os.path.join(PROJECT_ROOT, "server-rust", "target", "debug", f"vimcord-server{exe_suffix}"),
        os.path.join(PROJECT_ROOT, "target", "release", f"vimcord-server{exe_suffix}"),
        os.path.join(PROJECT_ROOT, "target", "debug", f"vimcord-server{exe_suffix}"),
        os.path.join(PROJECT_ROOT, f"vimcord-server{exe_suffix}"),
    ]
    for p in candidates:
        if os.path.isfile(p) and os.access(p, os.X_OK if sys.platform != "win32" else os.F_OK):
            return p
    return None

def run():
    rust_bin = find_rust_binary()
    if rust_bin:
        print(f"[INFO] Launching high-performance VimCord Rust Server: {rust_bin}")
        cmd = [rust_bin] + sys.argv[1:]
        try:
            if hasattr(os, "execv") and sys.platform != "win32":
                os.execv(rust_bin, cmd)
            else:
                sys.exit(subprocess.call(cmd))
        except Exception as e:
            print(f"[WARN] Failed to exec Rust server ({e}), falling back to Python...")

    # Fallback to Python server implementation
    sys.path.insert(0, PROJECT_ROOT)
    from vimcord.server.main import run as run_python
    run_python()

if __name__ == "__main__":
    run()
