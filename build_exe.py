"""
Build script to compile VimCord into a standalone single-file Windows executable.
"""
import sys
import os
import PyInstaller.__main__

def build():
    root_dir = os.path.dirname(os.path.abspath(__file__))
    dist_dir = os.path.join(root_dir, "dist")

    args = [
        os.path.join(root_dir, "run_client.py"),
        "--name=VimCord",
        "--noconsole",
        "--onefile",
        f"--icon={os.path.join(root_dir, 'icon.ico')}",
        f"--add-data={os.path.join(root_dir, 'icon.ico')};.",
        f"--add-data={os.path.join(root_dir, 'vimcord', 'resources')};vimcord/resources",
        f"--add-data={os.path.join(root_dir, 'vimcord', 'client', 'web')};vimcord/client/web",
        "--collect-all=win11toast",
        "--collect-all=webview",
        "--collect-all=pystray",
        "--collect-all=pynput",
        "--hidden-import=win11toast",
        "--hidden-import=webview",
        "--hidden-import=pystray",
        "--hidden-import=pynput",
        "--clean",
        "--noconfirm",
    ]

    print("Running PyInstaller with arguments:")
    print(" ".join(args))
    PyInstaller.__main__.run(args)

    exe_path = os.path.join(dist_dir, "VimCord.exe")
    if os.path.exists(exe_path):
        size_mb = os.path.getsize(exe_path) / (1024 * 1024)
        print(f"\n[SUCCESS] Standalone executable created successfully: {exe_path} ({size_mb:.2f} MB)")
        return True
    else:
        print(f"\n[ERROR] Executable not found at {exe_path}")
        return False

if __name__ == "__main__":
    success = build()
    sys.exit(0 if success else 1)
