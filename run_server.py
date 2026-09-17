#!/usr/bin/env python3
"""
Launcher script for VimCord Server.
Usage: python run_server.py [--host 0.0.0.0] [--tcp-port 9988] [--udp-port 9989]
"""
import sys
import os

# Ensure package is on sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from vimcord.server.main import run

if __name__ == "__main__":
    run()
