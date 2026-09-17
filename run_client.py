#!/usr/bin/env python3
"""
Launcher script for VimCord Client.
Usage:
    python run_client.py
    python run_client.py --user Alice
    python run_client.py --user Bob --auto
"""
import sys
import os

# Ensure package is on sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from vimcord.client.main import main

if __name__ == "__main__":
    main()
