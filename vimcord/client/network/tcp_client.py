"""
TCP Control Client for VimCord.
Runs network communication in a background thread and dispatches events via PyQt signals.
"""

import json
import logging
import socket
import threading
import time
from typing import Dict, Any, Optional
from PyQt6.QtCore import QObject, pyqtSignal
from vimcord.common.protocol import encode_json_message, decode_json_message

logger = logging.getLogger("VimCord.TCPClient")


class TCPClientSignals(QObject):
    connected = pyqtSignal()
    disconnected = pyqtSignal()
    error = pyqtSignal(str)

    # Server events
    login_response = pyqtSignal(bool, dict)  # success, full_resp_data
    user_presence = pyqtSignal(dict)         # user_dict
    room_created = pyqtSignal(dict)          # room_dict
    room_deleted = pyqtSignal(str)           # room_id
    channel_created = pyqtSignal(str, dict)  # room_id, channel_dict
    channel_deleted = pyqtSignal(str, str)   # room_id, channel_id
    voice_state_update = pyqtSignal(dict)    # dict with user_id, room_id, channel_id, action
    chat_message = pyqtSignal(dict)          # message dict
    
    # 1-on-1 Call events
    incoming_call = pyqtSignal(str, str, str)  # call_id, from_user_id, from_username
    call_ringing = pyqtSignal(str, str)        # call_id, target_user_id
    call_accepted = pyqtSignal(str, str, str)  # call_id, peer_id, peer_name
    call_declined = pyqtSignal(str)            # call_id
    call_ended = pyqtSignal(str)               # call_id
    call_failed = pyqtSignal(str)              # reason


class TCPClient:
    def __init__(self):
        self.signals = TCPClientSignals()
        self.sock: Optional[socket.socket] = None
        self._is_running: bool = False
        self._rx_thread: Optional[threading.Thread] = None
        self._write_lock = threading.Lock()

    def connect_to_server(self, host: str, port: int) -> bool:
        """Connects to VimCord TCP control server."""
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(5.0)
            self.sock.connect((host, port))
            self.sock.settimeout(None)
            self._is_running = True

            self._rx_thread = threading.Thread(target=self._receive_loop, daemon=True)
            self._rx_thread.start()

            self.signals.connected.emit()
            return True
        except Exception as e:
            logger.error(f"Failed to connect to {host}:{port} -> {e}")
            self.signals.error.emit(f"Не удалось подключиться к серверу: {e}")
            return False

    def disconnect(self):
        """Disconnects cleanly from the server."""
        self._is_running = False
        if self.sock:
            try:
                self.sock.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None
        self.signals.disconnected.emit()

    def send_message(self, msg: Dict[str, Any]):
        """Sends a JSON-encoded message line to the server."""
        if not self.sock or not self._is_running:
            return
        try:
            data = encode_json_message(msg)
            with self._write_lock:
                self.sock.sendall(data)
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            self.disconnect()

    def send_login(self, username: str):
        self.send_message({"type": "login", "username": username})

    def send_create_room(self, name: str):
        self.send_message({"type": "create_room", "name": name})

    def send_delete_room(self, room_id: str):
        self.send_message({"type": "delete_room", "room_id": room_id})

    def send_create_channel(self, room_id: str, name: str, channel_type: str):
        self.send_message({
            "type": "create_channel",
            "room_id": room_id,
            "name": name,
            "channel_type": channel_type
        })

    def send_delete_channel(self, room_id: str, channel_id: str):
        self.send_message({
            "type": "delete_channel",
            "room_id": room_id,
            "channel_id": channel_id
        })

    def send_join_voice(self, room_id: str, channel_id: str):
        self.send_message({
            "type": "join_voice",
            "room_id": room_id,
            "channel_id": channel_id
        })

    def send_leave_voice(self):
        self.send_message({"type": "leave_voice"})

    def send_chat_message(self, target_type: str, target_id: str, content: str):
        self.send_message({
            "type": "send_msg",
            "target_type": target_type,
            "target_id": target_id,
            "content": content
        })

    def send_call_start(self, target_user_id: str):
        self.send_message({"type": "call_start", "target_user_id": target_user_id})

    def send_call_accept(self, call_id: str):
        self.send_message({"type": "call_accept", "call_id": call_id})

    def send_call_decline(self, call_id: str):
        self.send_message({"type": "call_decline", "call_id": call_id})

    def send_call_end(self, call_id: str):
        self.send_message({"type": "call_end", "call_id": call_id})

    def _receive_loop(self):
        """Continuously reads newline-delimited JSON messages from the TCP socket."""
        buffer = ""
        while self._is_running and self.sock:
            try:
                data = self.sock.recv(4096)
                if not data:
                    break
                buffer += data.decode("utf-8", errors="ignore")
                
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if not line:
                        continue
                    msg = decode_json_message(line)
                    if msg:
                        self._dispatch_message(msg)

            except Exception as e:
                if self._is_running:
                    logger.debug(f"TCP recv error: {e}")
                break

        if self._is_running:
            self.disconnect()

    def _dispatch_message(self, msg: Dict[str, Any]):
        """Dispatches decoded message to corresponding PyQt signal."""
        mtype = msg.get("type")

        if mtype == "login_resp":
            self.signals.login_response.emit(msg.get("success", False), msg)

        elif mtype == "user_presence":
            self.signals.user_presence.emit(msg.get("user", {}))

        elif mtype == "room_created":
            self.signals.room_created.emit(msg.get("room", {}))

        elif mtype == "room_deleted":
            self.signals.room_deleted.emit(msg.get("room_id", ""))

        elif mtype == "channel_created":
            self.signals.channel_created.emit(msg.get("room_id", ""), msg.get("channel", {}))

        elif mtype == "channel_deleted":
            self.signals.channel_deleted.emit(msg.get("room_id", ""), msg.get("channel_id", ""))

        elif mtype == "voice_state_update":
            self.signals.voice_state_update.emit(msg)

        elif mtype == "new_msg":
            self.signals.chat_message.emit(msg)

        elif mtype == "incoming_call":
            self.signals.incoming_call.emit(
                msg.get("call_id", ""),
                msg.get("from_user_id", ""),
                msg.get("from_username", "")
            )

        elif mtype == "call_ringing":
            self.signals.call_ringing.emit(
                msg.get("call_id", ""),
                msg.get("target_user_id", "")
            )

        elif mtype == "call_accepted":
            self.signals.call_accepted.emit(
                msg.get("call_id", ""),
                msg.get("peer_id", ""),
                msg.get("peer_name", "")
            )

        elif mtype == "call_declined":
            self.signals.call_declined.emit(msg.get("call_id", ""))

        elif mtype == "call_ended":
            self.signals.call_ended.emit(msg.get("call_id", ""))

        elif mtype == "call_failed":
            self.signals.call_failed.emit(msg.get("reason", "Ошибка вызова"))
