"""
Thread-safe, lightweight Signal emitter replacing PyQt signals.
Supports .connect(), .disconnect(), and .emit().
"""

import logging
import threading
from typing import Callable, List

logger = logging.getLogger("VimCord.Signals")


class Signal:
    """
    Lightweight, thread-safe signal implementation matching PyQt pyqtSignal interface.
    """
    def __init__(self, *arg_types):
        self._arg_types = arg_types
        self._slots: List[Callable] = []
        self._lock = threading.Lock()

    def connect(self, slot: Callable):
        with self._lock:
            if slot not in self._slots:
                self._slots.append(slot)


    def disconnect(self, slot: Callable = None):
        with self._lock:
            if slot is None:
                self._slots.clear()
            elif slot in self._slots:
                self._slots.remove(slot)

    def emit(self, *args, **kwargs):
        with self._lock:
            slots_copy = list(self._slots)
        for slot in slots_copy:
            try:
                slot(*args, **kwargs)
            except Exception as e:
                logger.error(f"Error executing slot {slot}: {e}", exc_info=True)
