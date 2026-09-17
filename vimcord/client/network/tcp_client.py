"""
TCP Control Client for VimCord.
Runs network communication in a background thread and dispatches events via PyQt signals.
"""

import base64
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

    # Auth events
    register_response = pyqtSignal(bool, str)     # success, message
    login_response = pyqtSignal(bool, dict)       # success, full_resp_data
    user_presence = pyqtSignal(dict)              # user_dict

    # Rooms & channels
    room_created = pyqtSignal(dict)               # room_dict
    room_deleted = pyqtSignal(str)                # room_id
    channel_created = pyqtSignal(str, dict)       # room_id, channel_dict
    channel_deleted = pyqtSignal(str, str)        # room_id, channel_id
    voice_state_update = pyqtSignal(dict)         # dict with user_id, room_id, channel_id, action

    # Chat & history
    chat_message = pyqtSignal(dict)               # message dict
    history_response = pyqtSignal(str, str, list) # target_type, target_id, messages list

    # Invites & Friends
    room_invite_created = pyqtSignal(str, str)    # room_id, code
    room_invite_joined = pyqtSignal(bool, dict)   # success, room_data_or_error
    friends_update = pyqtSignal(list)             # list of friend dicts
    friend_request_resp = pyqtSignal(bool, str)   # success, message

    # Profile & settings
    profile_update_resp = pyqtSignal(bool, str, dict) # success, message, user_dict
    profile_resp = pyqtSignal(bool, dict)             # success, profile_dict_or_error
    user_media_state = pyqtSignal(dict)               # user_id, is_muted, is_deafened
    change_password_resp = pyqtSignal(bool, str)      # success, message

    # 1-on-1 Call events
    incoming_call = pyqtSignal(str, str, str)     # call_id, from_user_id, from_username
    call_ringing = pyqtSignal(str, str)           # call_id, target_user_id
    call_accepted = pyqtSignal(str, str, str)     # call_id, peer_id, peer_name
    call_declined = pyqtSignal(str)               # call_id
    call_ended = pyqtSignal(str)                  # call_id
    call_failed = pyqtSignal(str)                 # reason

    # Screen sharing
    screen_frame = pyqtSignal(str, bytes)         # sender_id, raw_jpeg_bytes
    screen_stop = pyqtSignal(str)                 # sender_id


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

    def send_register(self, username: str, password: str):
        self.send_message({"type": "register", "username": username, "password": password})

    def send_login(self, username: str, password: str = ""):
        self.send_message({"type": "login", "username": username, "password": password})

    def send_get_history(self, target_type: str, target_id: str):
        self.send_message({"type": "get_history", "target_type": target_type, "target_id": target_id})

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

    def send_create_room_invite(self, room_id: str):
        self.send_message({"type": "create_room_invite", "room_id": room_id})

    def send_join_room_by_invite(self, code: str):
        self.send_message({"type": "join_room_by_invite", "code": code})

    def send_friend_request(self, target_username: str):
        self.send_message({"type": "send_friend_request", "username": target_username})

    def send_accept_friend_request(self, sender_user_id: str):
        self.send_message({"type": "accept_friend_request", "sender_user_id": sender_user_id})

    def send_decline_friend_request(self, peer_id: str):
        self.send_message({"type": "decline_friend_request", "peer_id": peer_id})

    def send_update_profile(self, username: Optional[str] = None, status_text: Optional[str] = None, avatar_color: Optional[str] = None, avatar_image: Optional[str] = None):
        msg = {"type": "update_profile"}
        if username:
            msg["username"] = username
        if status_text is not None:
            msg["status_text"] = status_text
        if avatar_color:
            msg["avatar_color"] = avatar_color
        if avatar_image is not None:
            msg["avatar_image"] = avatar_image
        self.send_message(msg)

    def send_get_profile(self, user_id: str):
        self.send_message({"type": "get_profile", "user_id": user_id})

    def send_user_media_state(self, is_muted: bool, is_deafened: bool):
        self.send_message({"type": "user_media_state", "is_muted": is_muted, "is_deafened": is_deafened})

    def send_change_password(self, old_pass: str, new_pass: str):
        self.send_message({"type": "change_password", "old_password": old_pass, "new_password": new_pass})

    def send_join_voice(self, room_id: str, channel_id: str):
        self.send_message({"type": "join_voice", "room_id": room_id, "channel_id": channel_id})

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

    def send_screen_frame(self, target_type: str, target_id: str, jpeg_data: bytes):
        b64 = base64.b64encode(jpeg_data).decode("ascii")
        self.send_message({
            "type": "screen_frame",
            "target_type": target_type,
            "target_id": target_id,
            "data": b64
        })

    def send_screen_stop(self, target_type: str, target_id: str):
        self.send_message({
            "type": "screen_stop",
            "target_type": target_type,
            "target_id": target_id
        })

    def _receive_loop(self):
        buffer = ""
        while self._is_running and self.sock:
            try:
                data = self.sock.recv(65536)
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
        mtype = msg.get("type")

        if mtype == "register_resp":
            self.signals.register_response.emit(msg.get("success", False), msg.get("message", ""))

        elif mtype == "login_resp":
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

        elif mtype == "history_resp":
            self.signals.history_response.emit(
                msg.get("target_type", ""),
                msg.get("target_id", ""),
                msg.get("messages", [])
            )

        elif mtype == "room_invite_created":
            self.signals.room_invite_created.emit(msg.get("room_id", ""), msg.get("code", ""))

        elif mtype == "room_invite_joined":
            self.signals.room_invite_joined.emit(msg.get("success", False), msg)

        elif mtype == "friends_update":
            self.signals.friends_update.emit(msg.get("friends", []))

        elif mtype == "friend_request_resp":
            self.signals.friend_request_resp.emit(msg.get("success", False), msg.get("message", ""))

        elif mtype == "profile_update_resp":
            self.signals.profile_update_resp.emit(
                msg.get("success", False),
                msg.get("message", ""),
                msg.get("user", {})
            )

        elif mtype == "profile_resp":
            self.signals.profile_resp.emit(
                msg.get("success", False),
                msg.get("profile", {}) if msg.get("success", False) else {"error": msg.get("error", "")}
            )

        elif mtype == "user_media_state":
            self.signals.user_media_state.emit(msg)

        elif mtype == "change_password_resp":
            self.signals.change_password_resp.emit(msg.get("success", False), msg.get("message", ""))

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

        elif mtype == "screen_frame":
            sender_id = msg.get("sender_id", "")
            b64_data = msg.get("data", "")
            if sender_id and b64_data:
                try:
                    raw_jpeg = base64.b64decode(b64_data)
                    self.signals.screen_frame.emit(sender_id, raw_jpeg)
                except Exception:
                    pass

        elif mtype == "screen_stop":
            sender_id = msg.get("sender_id", "")
            if sender_id:
                self.signals.screen_stop.emit(sender_id)
