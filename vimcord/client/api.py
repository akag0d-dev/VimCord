"""
VimCord JavaScript Bridge API for pywebview.
Exposes all client operations (auth, chat, voice, calls, settings, files) to the web frontend.
"""

import base64
import json
import logging
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Dict, Any, Optional, List
from PIL import ImageGrab

from vimcord.client.audio.audio_manager import AudioManager
from vimcord.client.config import load_config, save_config, clear_auto_login, get_resource_path
from vimcord.client.i18n import set_language, get_language, t
from vimcord.client.input.global_hotkey import GlobalHotkeyManager
from vimcord.client.network.tcp_client import TCPClient
from vimcord.client.network.udp_voice import UDPVoiceClient
from vimcord.client.tray.tray_manager import TrayManager
from vimcord.client.video.screen_share import ScreenCapturer
from vimcord.common.protocol import DEFAULT_HOST, DEFAULT_TCP_PORT, DEFAULT_UDP_PORT

logger = logging.getLogger("VimCord.API")


class VimCordAPI:
    def __init__(self, window=None):
        self._window = window
        self._config = load_config()
        set_language(self._config.get("language", "en"))

        # Core subsystems (prefixed with _ so pywebview's get_functions does not inspect them recursively)
        self._audio_manager = AudioManager()
        self._tcp_client = TCPClient()
        self._udp_voice = UDPVoiceClient(self._audio_manager)
        self._screen_capturer = ScreenCapturer(send_func=self._udp_voice.send_screen_packet)
        self._screen_capturer.on_frame_ready = self._on_screen_frame_captured

        # State tracking
        self._my_user_id: str = ""
        self._my_username: str = ""
        self._my_display_name: str = ""
        self._my_avatar_color: str = "#5865F2"
        self._my_avatar_image: str = ""
        self._server_host: str = self._config.get("host", DEFAULT_HOST) or DEFAULT_HOST
        self._server_tcp_port: int = self._config.get("tcp_port", DEFAULT_TCP_PORT) or DEFAULT_TCP_PORT
        self._server_udp_port: int = self._config.get("udp_port", DEFAULT_UDP_PORT) or DEFAULT_UDP_PORT

        self._current_room_id: Optional[str] = None
        self._current_channel_id: Optional[str] = None
        self._current_dm_peer_id: Optional[str] = None
        self._current_voice_channel_id: Optional[str] = None
        self._active_call_id: Optional[str] = None
        self._is_muted: bool = False
        self._is_deafened: bool = False

        # Ping monitor
        self._ping_thread: Optional[threading.Thread] = None
        self._is_pinging: bool = False

        # Global Hotkey (PTT)
        self._hotkey_mgr = GlobalHotkeyManager(on_ptt_state_changed=self._on_ptt_state_changed)
        ptt_enabled = self._config.get("ptt_mode", False)
        ptt_key = self._config.get("ptt_key", "Space")
        self._audio_manager.set_ptt_mode(ptt_enabled)
        self._hotkey_mgr.set_ptt_config(ptt_enabled, ptt_key)
        self._hotkey_mgr.start()

        # Restore audio devices and settings
        in_dev = self._config.get("input_device")
        out_dev = self._config.get("output_device")
        if in_dev is not None:
            try:
                self._audio_manager.set_input_device(int(in_dev))
            except Exception:
                pass
        if out_dev is not None:
            try:
                self._audio_manager.set_output_device(int(out_dev))
            except Exception:
                pass
        if "mic_volume" in self._config:
            self._audio_manager.mic_volume = max(0.0, min(2.0, float(self._config["mic_volume"]) / 100.0))
        if "output_volume" in self._config:
            self._audio_manager.output_volume = max(0.0, min(2.0, float(self._config["output_volume"]) / 100.0))
        if "vad_threshold" in self._config:
            self._audio_manager.vad_threshold = float(self._config["vad_threshold"])

        # Tray Manager
        self._tray = TrayManager(on_open=self._on_tray_open, on_quit=self.quit_app)
        self._tray.start()

        # Hook audio events
        self._audio_manager.on_speaking_changed = self._on_local_speaking_changed

        # Hook network events
        self._bind_network_signals()

    def set_window(self, window):
        self._window = window

    def dispatch_event(self, event_name: str, payload: Any = None):
        """Sends an event asynchronously to JavaScript on the main window."""
        if not self._window:
            return
        try:
            js = f"window.onVimCordEvent({json.dumps(event_name)}, {json.dumps(payload)});"
            self._window.evaluate_js(js)
        except Exception as e:
            logger.debug(f"Failed to dispatch event {event_name}: {e}")

    def _bind_network_signals(self):
        s = self._tcp_client.signals
        s.connected.connect(lambda: self.dispatch_event("connected"))
        s.disconnected.connect(lambda: self.dispatch_event("disconnected"))
        s.error.connect(lambda msg: self.dispatch_event("network_error", msg))
        s.login_response.connect(self._on_login_response)
        s.register_response.connect(lambda ok, msg: self.dispatch_event("register_response", {"success": ok, "message": msg}))
        s.user_presence.connect(lambda user: self.dispatch_event("user_presence", user))
        s.room_created.connect(lambda room: self.dispatch_event("room_created", room))
        s.room_deleted.connect(lambda rid: self.dispatch_event("room_deleted", rid))
        s.channel_created.connect(lambda rid, ch: self.dispatch_event("channel_created", {"room_id": rid, "channel": ch}))
        s.channel_deleted.connect(lambda rid, cid: self.dispatch_event("channel_deleted", {"room_id": rid, "channel_id": cid}))
        s.channel_renamed.connect(lambda rid, cid, name: self.dispatch_event("channel_renamed", {"room_id": rid, "channel_id": cid, "name": name}))
        s.voice_state_update.connect(lambda v: self.dispatch_event("voice_state_update", v))
        s.voice_channel_sync.connect(lambda v: self.dispatch_event("voice_channel_sync", v))
        s.chat_message.connect(self._on_incoming_chat_message)
        s.message_deleted.connect(lambda mid, tt, tid: self.dispatch_event("message_deleted", {"msg_id": mid, "target_type": tt, "target_id": tid}))
        s.history_response.connect(lambda tt, tid, msgs: self.dispatch_event("history_response", {"target_type": tt, "target_id": tid, "messages": msgs}))
        s.friends_update.connect(lambda fl: self.dispatch_event("friends_update", fl))
        s.friend_request_resp.connect(lambda ok, msg: self.dispatch_event("friend_request_resp", {"success": ok, "message": msg}))
        s.room_invite_created.connect(lambda rid, code: self.dispatch_event("room_invite_created", {"room_id": rid, "code": code}))
        s.room_invite_joined.connect(lambda ok, data: self.dispatch_event("room_invite_joined", {"success": ok, "data": data}))
        s.leave_room_resp.connect(lambda ok, msg, rid: self.dispatch_event("leave_room_resp", {"success": ok, "message": msg, "room_id": rid}))
        s.room_members_resp.connect(lambda rid, members: self.dispatch_event("room_members_resp", {"room_id": rid, "members": members}))
        s.pong.connect(self._on_pong)
        s.profile_update_resp.connect(lambda ok, msg, user: self.dispatch_event("profile_update_resp", {"success": ok, "message": msg, "user": user}))
        s.user_media_state.connect(lambda u: self.dispatch_event("user_media_state", u))
        s.change_password_resp.connect(lambda ok, msg: self.dispatch_event("change_password_resp", {"success": ok, "message": msg}))

        # Calls
        s.incoming_call.connect(self._on_incoming_call)
        s.call_ringing.connect(lambda cid, tid: self.dispatch_event("call_ringing", {"call_id": cid, "target_id": tid}))
        s.call_accepted.connect(self._on_call_accepted)
        s.call_declined.connect(self._on_call_declined)
        s.call_ended.connect(self._on_call_ended)
        s.call_failed.connect(self._on_call_failed)

        # Screen sharing
        s.screen_frame.connect(lambda sid, b: self._on_received_screen_frame(sid, b))
        s.screen_stop.connect(lambda sid: self.dispatch_event("screen_stop", {"sender_id": sid}))
        self._udp_voice.signals.screen_frame_received.connect(lambda sid, b: self._on_received_screen_frame(sid, b))

        # UDP Voice speaking
        self._udp_voice.signals.peer_speaking.connect(lambda uid, spk: self.dispatch_event("peer_speaking", {"user_id": uid, "is_speaking": spk}))

    # ---------------- UI & Window Actions ----------------

    def get_initial_state(self) -> Dict[str, Any]:
        """Returns loaded config, localization, audio devices, and user state."""
        cfg = load_config()
        return {
            "config": cfg,
            "language": get_language(),
            "audio_devices": self.get_audio_devices(),
            "input_device": cfg.get("input_device"),
            "output_device": cfg.get("output_device"),
            "theme": cfg.get("theme", "dark"),
            "ptt_mode": self._audio_manager.ptt_mode,
            "ptt_key": getattr(self._hotkey_mgr, "ptt_key", "Space"),
            "mic_volume": int(getattr(self._audio_manager, "mic_volume", 1.0) * 100),
            "output_volume": int(getattr(self._audio_manager, "output_volume", 1.0) * 100),
            "vad_threshold": getattr(self._audio_manager, "vad_threshold", 0.005),
            "dnd_mode": cfg.get("dnd_mode", False),
            "stream_resolution": cfg.get("stream_resolution", "720p"),
            "stream_fps": cfg.get("stream_fps", 15),
            "stream_quality": cfg.get("stream_quality", 45),
            "auto_login": cfg.get("auto_login", False),
            "saved_username": cfg.get("username", "") or cfg.get("saved_username", ""),
            "saved_password": cfg.get("saved_password", "") if cfg.get("auto_login") else ""
        }

    def minimize_window(self):
        if self._window:
            self._window.minimize()

    def toggle_maximize_window(self):
        if self._window:
            self._window.toggle_fullscreen()

    def close_window(self):
        """Minimize window to tray on close button click."""
        if self._window:
            self._window.hide()

    def set_window_size(self, width: int, height: int):
        self._resize_window(width, height)

    def _resize_window(self, width: int, height: int):
        if not self._window:
            return
        try:
            self._window.resize(width, height)
            import webview
            screens = webview.screens
            if screens:
                s = screens[0]
                x = max(0, (s.width - width) // 2)
                y = max(0, (s.height - height) // 2)
                self._window.move(x, y)
        except Exception as e:
            logger.debug(f"Failed to resize window: {e}")

    def quit_app(self):
        """Completely terminates VimCord and cleans up all background threads."""
        self._hotkey_mgr.stop()
        self._tray.stop()
        self._screen_capturer.stop_sharing()
        if self._current_voice_channel_id:
            try:
                self._tcp_client.send_leave_voice()
            except Exception:
                pass
        if self._active_call_id:
            try:
                self._tcp_client.send_call_end(self._active_call_id)
            except Exception:
                pass
        self._tcp_client.disconnect()
        self._udp_voice.stop()
        self._audio_manager.stop()
        if self._window:
            try:
                self._window.destroy()
            except Exception:
                pass
        os._exit(0)

    def _on_tray_open(self):
        if self._window:
            self._window.show()
            self._window.restore()

    # ---------------- Auth & Connection ----------------

    def login(self, username: str, password: str = "", host: str = "", tcp_port: int = 0, udp_port: int = 0, auto_login: bool = False):
        if isinstance(host, str) and host.strip():
            self._server_host = host.strip()
        elif not isinstance(self._server_host, str) or not self._server_host:
            self._server_host = DEFAULT_HOST

        if isinstance(tcp_port, int) and tcp_port > 0:
            self._server_tcp_port = tcp_port
        elif not isinstance(self._server_tcp_port, int) or self._server_tcp_port <= 0:
            self._server_tcp_port = DEFAULT_TCP_PORT

        if isinstance(udp_port, int) and udp_port > 0:
            self._server_udp_port = udp_port
        elif not isinstance(self._server_udp_port, int) or self._server_udp_port <= 0:
            self._server_udp_port = DEFAULT_UDP_PORT

        # Update saved connection config
        cfg_updates = {
            "host": self._server_host,
            "tcp_port": self._server_tcp_port,
            "udp_port": self._server_udp_port,
            "username": username,
            "auto_login": auto_login
        }
        if auto_login and password:
            cfg_updates["saved_password"] = password
        save_config(cfg_updates)

        # Fresh connection to server
        if not self._tcp_client.sock or not self._tcp_client._is_running:
            self._tcp_client.disconnect()
            ok = self._tcp_client.connect_to_server(self._server_host, self._server_tcp_port)
            if not ok:
                err_msg = f"Could not connect to server at {self._server_host}:{self._server_tcp_port}"
                self.dispatch_event("login_response", {"success": False, "data": {"message": err_msg}})
                return {"success": False, "message": err_msg}

        try:
            self._tcp_client.send_login(username, password)
            return {"success": True, "pending": True}
        except Exception as e:
            err_msg = f"Failed to send login: {e}"
            self.dispatch_event("login_response", {"success": False, "data": {"message": err_msg}})
            return {"success": False, "message": err_msg}

    def register(self, username: str, password: str = "", host: str = "", tcp_port: int = 0, udp_port: int = 0):
        if isinstance(host, str) and host.strip():
            self._server_host = host.strip()
        elif not isinstance(self._server_host, str) or not self._server_host:
            self._server_host = DEFAULT_HOST

        if isinstance(tcp_port, int) and tcp_port > 0:
            self._server_tcp_port = tcp_port
        elif not isinstance(self._server_tcp_port, int) or self._server_tcp_port <= 0:
            self._server_tcp_port = DEFAULT_TCP_PORT

        if isinstance(udp_port, int) and udp_port > 0:
            self._server_udp_port = udp_port
        elif not isinstance(self._server_udp_port, int) or self._server_udp_port <= 0:
            self._server_udp_port = DEFAULT_UDP_PORT

        if not self._tcp_client.sock or not self._tcp_client._is_running:
            self._tcp_client.disconnect()
            ok = self._tcp_client.connect_to_server(self._server_host, self._server_tcp_port)
            if not ok:
                err_msg = f"Could not connect to server at {self._server_host}:{self._server_tcp_port}"
                self.dispatch_event("register_response", {"success": False, "message": err_msg})
                return {"success": False, "message": err_msg}

        try:
            self._tcp_client.send_register(username, password)
            return {"success": True, "pending": True}
        except Exception as e:
            err_msg = f"Failed to send register: {e}"
            self.dispatch_event("register_response", {"success": False, "message": err_msg})
            return {"success": False, "message": err_msg}

    def logout(self):
        """Logs out of current session, clears auto_login, and resets window size to login size."""
        clear_auto_login()
        if self._current_voice_channel_id:
            try:
                self._tcp_client.send_leave_voice()
            except Exception:
                pass
        if self._active_call_id:
            try:
                self._tcp_client.send_call_end(self._active_call_id)
            except Exception:
                pass
        self._is_pinging = False
        self._tcp_client.disconnect()
        self._udp_voice.stop()
        self._audio_manager.stop()
        self._resize_window(460, 620)

    def _on_login_response(self, ok: bool, data: dict):
        if ok:
            self._my_user_id = data.get("user_id", "")
            self._my_username = data.get("username", "")
            self._my_display_name = data.get("display_name", "") or self._my_username
            self._my_avatar_color = data.get("avatar_color", "#5865F2")
            self._my_avatar_image = data.get("avatar_image", "")

            # Start audio subsystems
            self._audio_manager.start()
            self._udp_voice.start(self._my_user_id, self._server_host, self._server_udp_port)

            # Start ping loop
            self._start_ping_loop()

            # Expand window to full Discord workspace
            self._resize_window(1280, 800)

        self.dispatch_event("login_response", {"success": ok, "data": data})

    def _start_ping_loop(self):
        if self._is_pinging:
            return
        self._is_pinging = True

        def loop():
            while self._is_pinging:
                if self._tcp_client.sock and self._tcp_client._is_running:
                    try:
                        self._tcp_client.send_ping(time.time())
                    except Exception:
                        pass
                time.sleep(3.0)

        self._ping_thread = threading.Thread(target=loop, daemon=True)
        self._ping_thread.start()

    def _on_pong(self, sent_time: float):
        rtt_ms = int(max(1.0, (time.time() - sent_time) * 1000.0))
        self.dispatch_event("pong", {"ping_ms": rtt_ms})

    # ---------------- Chat, Files & Clipboard ----------------

    def send_chat_message(self, target_type: str, target_id: str, content: str = "",
                          image_data: str = "", voice_data: str = "", voice_duration: float = 0.0,
                          file_data: str = "", file_name: str = "", file_size: int = 0):
        """Sends a message asynchronously in a background thread to prevent any UI freezing."""
        msg_id = f"m-{uuid.uuid4().hex[:8]}"

        local_msg = {
            "msg_id": msg_id,
            "sender_id": self._my_user_id,
            "sender_name": self._my_display_name or self._my_username,
            "target_type": target_type,
            "target_id": target_id,
            "content": content,
            "image_data": image_data,
            "voice_data": voice_data,
            "voice_duration": voice_duration,
            "file_data": file_data,
            "file_name": file_name,
            "file_size": file_size,
            "timestamp": time.time(),
            "pending": False
        }

        # Send through TCPClient with async background socket write
        self._tcp_client.send_chat_message(
            target_type=target_type,
            target_id=target_id,
            content=content,
            image_data=image_data,
            voice_data=voice_data,
            voice_duration=voice_duration,
            file_data=file_data,
            file_name=file_name,
            file_size=file_size,
            msg_id=msg_id
        )

        return local_msg

    def delete_message(self, msg_id: str, target_type: str, target_id: str):
        self._tcp_client.send_delete_message(msg_id, target_type, target_id)

    def get_history(self, target_type: str, target_id: str):
        self._tcp_client.send_get_history(target_type, target_id)

    def _on_incoming_chat_message(self, msg: Dict[str, Any]):
        sender_id = msg.get("sender_id")
        if sender_id != self._my_user_id:
            self._audio_manager.play_message_chime()
        self.dispatch_event("chat_message", msg)

    def open_file_dialog(self) -> Optional[Dict[str, Any]]:
        """Opens native file chooser dialog via pywebview."""
        if not self._window:
            return None
        import webview
        files = self._window.create_file_dialog(webview.OPEN_DIALOG, allow_multiple=False)
        if not files or not len(files):
            return None
        file_path = files[0]
        if not os.path.exists(file_path):
            return None

        size = os.path.getsize(file_path)
        if size > 25 * 1024 * 1024:
            return {"error": "File exceeds 25 MB limit"}

        filename = os.path.basename(file_path)
        ext = os.path.splitext(filename)[1].lower()
        is_image = ext in (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif")

        try:
            with open(file_path, "rb") as f:
                raw = f.read()
            b64_str = base64.b64encode(raw).decode("ascii")
            return {
                "name": filename,
                "size": size,
                "is_image": is_image,
                "data": b64_str
            }
        except Exception as e:
            return {"error": str(e)}

    def save_file_to_disk(self, filename: str, b64_data: str) -> Dict[str, Any]:
        """Saves file to OS Downloads folder."""
        try:
            raw_bytes = base64.b64decode(b64_data)
            downloads_dir = Path.home() / "Downloads"
            downloads_dir.mkdir(parents=True, exist_ok=True)
            target_path = downloads_dir / filename

            # Deduplicate filename if exists
            base_stem = target_path.stem
            ext = target_path.suffix
            counter = 1
            while target_path.exists():
                target_path = downloads_dir / f"{base_stem}_{counter}{ext}"
                counter += 1

            with open(target_path, "wb") as f:
                f.write(raw_bytes)

            return {"success": True, "path": str(target_path)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_clipboard_image(self) -> Optional[Dict[str, Any]]:
        """Grabs image from OS clipboard using PIL ImageGrab as a backup/helper."""
        try:
            img = ImageGrab.grabclipboard()
            if img and hasattr(img, "save"):
                import io
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                b64 = base64.b64encode(buf.getvalue()).decode("ascii")
                return {
                    "name": "clipboard_image.png",
                    "size": len(buf.getvalue()),
                    "is_image": True,
                    "data": b64
                }
        except Exception as e:
            logger.debug(f"Failed to grab clipboard image: {e}")
        return None

    # ---------------- Voice Recording & Playback ----------------

    def start_voice_record(self):
        self._audio_manager.start_recording_voice_msg()

    def stop_voice_record(self) -> Dict[str, Any]:
        b64, dur = self._audio_manager.stop_recording_voice_msg()
        return {"data": b64, "duration": dur}

    def play_voice_message(self, voice_data: str, duration: float = 0.0):
        self._audio_manager.play_voice_msg(voice_data, duration)

    # ---------------- Direct Calls & Voice Channels ----------------

    def join_voice(self, room_id: str, channel_id: str):
        if self._current_voice_channel_id and self._current_voice_channel_id != channel_id:
            try:
                self._tcp_client.send_leave_voice()
            except Exception:
                pass
        self._current_voice_channel_id = channel_id
        self._current_room_id = room_id
        self._udp_voice.current_channel_id = channel_id
        self._tcp_client.send_join_voice(room_id, channel_id)
        self._audio_manager.play_join_chime()

    def leave_voice(self):
        if self._screen_capturer.is_sharing:
            self._screen_capturer.stop_sharing()
        if self._active_call_id:
            self.end_call()
        if self._current_voice_channel_id:
            self._tcp_client.send_leave_voice()
            self._current_voice_channel_id = None
            self._udp_voice.current_channel_id = None
            self._audio_manager.clear_peers()
            self._audio_manager.play_leave_chime()
            self._tray.update_speaking(False)

    def start_call(self, target_user_id: str):
        self._audio_manager.start_ringtone("outgoing")
        self._tcp_client.send_call_start(target_user_id)

    def accept_call(self, call_id: str):
        self._audio_manager.stop_ringtone()
        self._active_call_id = call_id
        self._udp_voice.current_channel_id = call_id
        self._tcp_client.send_call_accept(call_id)

    def decline_call(self, call_id: str):
        self._audio_manager.stop_ringtone()
        self._tcp_client.send_call_decline(call_id)

    def end_call(self):
        self._audio_manager.stop_ringtone()
        if self._active_call_id:
            self._tcp_client.send_call_end(self._active_call_id)
            self._active_call_id = None
            self._udp_voice.current_channel_id = None
            self._audio_manager.clear_peers()
            self._tray.update_speaking(False)
            self.dispatch_event("call_ended", {"call_id": None})

    def _on_incoming_call(self, call_id: str, from_user_id: str, from_username: str):
        self._active_call_id = call_id
        self._audio_manager.start_ringtone("incoming")
        self.dispatch_event("incoming_call", {
            "call_id": call_id,
            "from_user_id": from_user_id,
            "from_username": from_username
        })

    def _on_call_accepted(self, call_id: str, peer_id: str, peer_name: str):
        self._audio_manager.stop_ringtone()
        self._active_call_id = call_id
        self._udp_voice.current_channel_id = call_id
        self.dispatch_event("call_accepted", {
            "call_id": call_id,
            "peer_id": peer_id,
            "peer_name": peer_name
        })

    def _on_call_declined(self, call_id: str):
        self._audio_manager.stop_ringtone()
        self._active_call_id = None
        self._udp_voice.current_channel_id = None
        self.dispatch_event("call_declined", {"call_id": call_id})

    def _on_call_ended(self, call_id: str):
        self._audio_manager.stop_ringtone()
        self._active_call_id = None
        self._udp_voice.current_channel_id = None
        self._audio_manager.clear_peers()
        self._tray.update_speaking(False)
        self.dispatch_event("call_ended", {"call_id": call_id})

    def _on_call_failed(self, reason: str):
        self._audio_manager.stop_ringtone()
        self._active_call_id = None
        self._udp_voice.current_channel_id = None
        self.dispatch_event("call_failed", {"reason": reason})

    # ---------------- Audio & Settings ----------------

    def set_mic_muted(self, muted: bool):
        self._is_muted = bool(muted)
        self._audio_manager.set_muted(self._is_muted)
        self._tcp_client.send_user_media_state(self._is_muted, self._is_deafened)

    def set_deafened(self, deafened: bool):
        self._is_deafened = bool(deafened)
        self._audio_manager.set_deafened(self._is_deafened)
        self._tcp_client.send_user_media_state(self._is_muted, self._is_deafened)

    def set_peer_volume(self, peer_id: str, volume: float):
        self._audio_manager.set_peer_volume(peer_id, volume)

    def set_peer_muted(self, peer_id: str, muted: bool):
        self._audio_manager.set_peer_muted(peer_id, muted)

    def set_mic_volume(self, volume: float):
        vol = max(0.0, min(2.0, float(volume)))
        self._audio_manager.mic_volume = vol
        save_config({"mic_volume": int(vol * 100)})

    def set_output_volume(self, volume: float):
        vol = max(0.0, min(2.0, float(volume)))
        self._audio_manager.output_volume = vol
        save_config({"output_volume": int(vol * 100)})

    def set_vad_threshold(self, threshold: float):
        thresh = max(0.001, min(0.2, float(threshold)))
        self._audio_manager.vad_threshold = thresh
        save_config({"vad_threshold": thresh})

    def start_mic_test(self):
        self._audio_manager.loopback_test = True
        def intercept(rms, speaking):
            pct = min(100, int(rms * 600))
            self.dispatch_event("mic_test_level", {"level": pct, "speaking": speaking})
        self._audio_manager.on_mic_level = intercept

    def stop_mic_test(self):
        self._audio_manager.loopback_test = False
        self._audio_manager.on_mic_level = None
        self.dispatch_event("mic_test_level", {"level": 0, "speaking": False})

    def set_stream_settings(self, resolution: str, fps: int, quality: int):
        self._screen_capturer.set_stream_settings(resolution, fps, quality)
        save_config({
            "stream_resolution": resolution,
            "stream_fps": int(fps),
            "stream_quality": int(quality)
        })

    def set_dnd_mode(self, enabled: bool):
        save_config({"dnd_mode": bool(enabled)})
        self.dispatch_event("dnd_changed", {"enabled": bool(enabled)})

    # ---------------- Screen Sharing ----------------

    def start_screen_share(self, target_type: str, target_id: str):
        self._screen_capturer.start_sharing(self._my_user_id, target_id, target_type)

    def stop_screen_share(self, target_type: str = "channel", target_id: str = ""):
        self._screen_capturer.stop_sharing()
        if hasattr(self._udp_voice, "stop_screen_share"):
            self._udp_voice.stop_screen_share()
        if target_id:
            try:
                self._tcp_client.send_screen_stop(target_type, target_id)
            except Exception:
                pass

    def _on_screen_frame_captured(self, target_type: str, target_id: str, jpeg_data: bytes):
        # Prevent TCP socket buffer buildup and ping spikes by dropping frames if network transmission is busy
        if getattr(self, "_is_transmitting_screen_frame", False):
            return
        self._is_transmitting_screen_frame = True

        def _send_worker():
            try:
                self._tcp_client.send_screen_frame(target_type, target_id, jpeg_data)
            except Exception as e:
                logger.debug(f"Failed to send screen frame: {e}")
            finally:
                self._is_transmitting_screen_frame = False

        threading.Thread(target=_send_worker, daemon=True).start()

        # Throttle local frame dispatch so evaluate_js does not flood WebView2
        now = time.time()
        if not hasattr(self, "_last_local_preview_time") or (now - self._last_local_preview_time) > 0.08:
            self._last_local_preview_time = now
            b64 = base64.b64encode(jpeg_data).decode("ascii")
            self.dispatch_event("local_screen_frame", {"frame": b64})

    def _on_received_screen_frame(self, sender_id: str, jpeg_bytes: bytes):
        b64 = base64.b64encode(jpeg_bytes).decode("ascii")
        self.dispatch_event("screen_frame", {"sender_id": sender_id, "frame": b64})

    # ---------------- Audio Subsystems & Devices ----------------

    def get_audio_devices(self) -> Dict[str, Any]:
        return self._audio_manager.get_available_devices()

    def set_audio_devices(self, input_device: Optional[int], output_device: Optional[int]):
        updates = {}
        if input_device is not None:
            self._audio_manager.set_input_device(input_device)
            updates["input_device"] = input_device
        if output_device is not None:
            self._audio_manager.set_output_device(output_device)
            updates["output_device"] = output_device
        if updates:
            save_config(updates)

    def set_ptt_config(self, enabled: bool, hotkey: str):
        self._audio_manager.set_ptt_mode(enabled)
        self._hotkey_mgr.set_ptt_config(enabled, hotkey)
        save_config({"ptt_mode": enabled, "ptt_key": hotkey})

    def record_keybind_start(self):
        def on_captured(key_name: str):
            self.set_ptt_config(True, key_name)
            self.dispatch_event("keybind_captured", {"key": key_name})
        self._hotkey_mgr.start_recording(on_captured)

    def _on_ptt_state_changed(self, is_active: bool):
        self._audio_manager.set_ptt_active(is_active)
        self.dispatch_event("ptt_active_changed", {"active": is_active})

    def _on_local_speaking_changed(self, is_speaking: bool):
        self._tray.update_speaking(is_speaking)
        self.dispatch_event("local_speaking", {"is_speaking": is_speaking})

    def set_theme(self, theme_name: str):
        save_config({"theme": theme_name})

    def set_language(self, lang: str):
        set_language(lang)
        save_config({"language": lang})
        self._tray.update_language()
        self.dispatch_event("language_changed", {"language": lang})

    def update_profile(self, display_name: str = "", status_text: str = "",
                       avatar_color: str = "", banner_color: str = "",
                       avatar_image: str = "", banner_image: str = "", bio: str = ""):
        self._my_display_name = display_name or self._my_display_name
        self._my_avatar_color = avatar_color or self._my_avatar_color
        self._my_avatar_image = avatar_image or self._my_avatar_image
        self._tcp_client.send_update_profile(
            display_name=display_name,
            status_text=status_text,
            avatar_color=avatar_color,
            banner_color=banner_color,
            avatar_image=avatar_image,
            banner_image=banner_image,
            bio=bio
        )

    def change_password(self, old_pass: str, new_pass: str):
        self._tcp_client.send_change_password(old_pass, new_pass)

    # ---------------- Server & Room Navigation ----------------

    def create_room(self, name: str):
        self._tcp_client.send_create_room(name)

    def delete_room(self, room_id: str):
        self._tcp_client.send_delete_room(room_id)

    def leave_room(self, room_id: str):
        self._tcp_client.send_leave_room(room_id)

    def create_channel(self, room_id: str, name: str, channel_type: str = "text"):
        self._tcp_client.send_create_channel(room_id, name, channel_type)

    def rename_channel(self, room_id: str, channel_id: str, name: str):
        self._tcp_client.send_rename_channel(room_id, channel_id, name)

    def delete_channel(self, room_id: str, channel_id: str):
        self._tcp_client.send_delete_channel(room_id, channel_id)

    def create_room_invite(self, room_id: str):
        self._tcp_client.send_create_room_invite(room_id)

    def join_room_by_invite(self, code: str):
        self._tcp_client.send_join_room_by_invite(code)

    def get_room_members(self, room_id: str):
        self._tcp_client.send_get_room_members(room_id)

    def send_friend_request(self, username: str):
        self._tcp_client.send_friend_request(username)

    def accept_friend_request(self, sender_id: str):
        self._tcp_client.send_accept_friend_request(sender_id)

    def decline_friend_request(self, peer_id: str):
        self._tcp_client.send_decline_friend_request(peer_id)

    def reconnect(self):
        """Attempts to reconnect using saved credentials."""
        if self._my_username:
            cfg = load_config()
            pwd = cfg.get("saved_password", "")
            threading.Thread(target=lambda: self.login(self._my_username, pwd, True), daemon=True).start()
