"""
Main Window for VimCord.
Assembles the navigation rail, sidebar, voice stage, text chat, user panel, and call modals.
"""

import logging
from typing import Dict, Any, List, Optional
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QSplitter,
    QInputDialog, QMessageBox
)

from vimcord.client.audio.audio_manager import AudioManager
from vimcord.client.network.tcp_client import TCPClient
from vimcord.client.network.udp_voice import UDPVoiceClient
from vimcord.client.ui.server_nav import ServerNavBar
from vimcord.client.ui.channel_list import ChannelListWidget
from vimcord.client.ui.user_panel import UserPanel
from vimcord.client.ui.voice_view import VoiceView
from vimcord.client.ui.chat_view import ChatView
from vimcord.client.ui.call_overlay import IncomingCallDialog, ActiveCallBanner
from vimcord.client.ui.settings_dialog import SettingsDialog

logger = logging.getLogger("VimCord.MainWindow")


class MainWindow(QMainWindow):
    def __init__(self, tcp_client: TCPClient, audio_manager: AudioManager, udp_voice: UDPVoiceClient):
        super().__init__()
        self.tcp_client = tcp_client
        self.audio_manager = audio_manager
        self.udp_voice = udp_voice

        # User state
        self.my_user_id = ""
        self.my_username = ""
        self.server_host = "127.0.0.1"
        self.server_udp_port = 9989

        # Cache of rooms and users
        self.rooms: Dict[str, Dict[str, Any]] = {}
        self.users: Dict[str, Dict[str, Any]] = {}
        self.current_room_id: Optional[str] = None  # None = @me (DMs)
        self.current_text_channel_id: Optional[str] = None
        self.current_dm_peer_id: Optional[str] = None
        self.current_voice_channel_id: Optional[str] = None

        # Incoming call modal reference
        self.incoming_dialog: Optional[IncomingCallDialog] = None
        self.active_call_id: Optional[str] = None
        self.active_call_peer_name: str = ""

        self.setWindowTitle("VimCord")
        self.resize(1100, 720)
        self.setMinimumSize(850, 550)

        self._init_ui()
        self._bind_signals()

    def _init_ui(self):
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)

        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 1. Leftmost server navigation bar (72px)
        self.server_nav = ServerNavBar(self)
        main_layout.addWidget(self.server_nav)

        # 2. Sidebar container (Channel list + User panel at bottom) (240px)
        sidebar_container = QWidget()
        sidebar_container.setFixedWidth(240)
        sidebar_container.setStyleSheet("background-color: #2b2d31;")
        sidebar_layout = QVBoxLayout(sidebar_container)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(0)

        self.channel_list = ChannelListWidget(sidebar_container)
        sidebar_layout.addWidget(self.channel_list, 1)

        self.user_panel = UserPanel(sidebar_container)
        sidebar_layout.addWidget(self.user_panel)

        main_layout.addWidget(sidebar_container)

        # 3. Main content area (Splitter with Voice Stage and Chat View)
        self.content_container = QWidget()
        self.content_container.setStyleSheet("background-color: #313338;")
        content_layout = QVBoxLayout(self.content_container)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        # Active 1-on-1 call banner
        self.call_banner = ActiveCallBanner(self.content_container)
        self.call_banner.hide()
        content_layout.addWidget(self.call_banner)

        # Splitter for Voice View and Chat View
        self.splitter = QSplitter(Qt.Orientation.Vertical)
        self.splitter.setStyleSheet("QSplitter::handle { background-color: #1f2023; height: 3px; }")

        self.voice_view = VoiceView(self.splitter)
        self.voice_view.hide()
        self.splitter.addWidget(self.voice_view)

        self.chat_view = ChatView(self.splitter)
        self.splitter.addWidget(self.chat_view)

        content_layout.addWidget(self.splitter, 1)
        main_layout.addWidget(self.content_container, 1)

    def _bind_signals(self):
        # Navigation signals
        self.server_nav.dm_selected.connect(self._on_dm_nav_selected)
        self.server_nav.room_selected.connect(self._on_room_nav_selected)
        self.server_nav.create_room_requested.connect(self._on_create_room_prompt)

        # Sidebar signals
        self.channel_list.text_channel_selected.connect(self._on_text_channel_selected)
        self.channel_list.voice_channel_selected.connect(self._on_voice_channel_selected)
        self.channel_list.create_channel_requested.connect(self._on_create_channel_prompt)
        self.channel_list.delete_room_requested.connect(self._on_delete_room)
        self.channel_list.dm_user_selected.connect(self._on_dm_user_selected)
        self.channel_list.call_user_requested.connect(self._on_call_user_requested)

        # User panel signals
        self.user_panel.mic_toggled.connect(self._on_mic_toggled)
        self.user_panel.deafen_toggled.connect(self._on_deafen_toggled)
        self.user_panel.settings_clicked.connect(self._on_settings_clicked)

        # Voice stage signals
        self.voice_view.disconnect_clicked.connect(self._on_disconnect_voice)
        self.call_banner.end_call_clicked.connect(self._on_end_active_call)

        # Chat view signals
        self.chat_view.send_message_requested.connect(self._on_send_chat_message)

        # TCP Client signals
        self.tcp_client.signals.disconnected.connect(self._on_server_disconnected)
        self.tcp_client.signals.user_presence.connect(self._on_user_presence)
        self.tcp_client.signals.room_created.connect(self._on_room_created)
        self.tcp_client.signals.room_deleted.connect(self._on_room_deleted)
        self.tcp_client.signals.channel_created.connect(self._on_channel_created)
        self.tcp_client.signals.channel_deleted.connect(self._on_channel_deleted)
        self.tcp_client.signals.voice_state_update.connect(self._on_voice_state_update)
        self.tcp_client.signals.chat_message.connect(self._on_chat_message_received)
        self.tcp_client.signals.incoming_call.connect(self._on_incoming_call)
        self.tcp_client.signals.call_ringing.connect(self._on_call_ringing)
        self.tcp_client.signals.call_accepted.connect(self._on_call_accepted)
        self.tcp_client.signals.call_declined.connect(self._on_call_declined)
        self.tcp_client.signals.call_ended.connect(self._on_call_ended)
        self.tcp_client.signals.call_failed.connect(self._on_call_failed)

        # UDP Voice signals
        self.udp_voice.signals.peer_speaking.connect(self._on_peer_speaking)

    def initialize_session(self, user_id: str, username: str, rooms: List[Dict], users: List[Dict], host: str, udp_port: int):
        """Called after successful login."""
        self.my_user_id = user_id
        self.my_username = username
        self.server_host = host
        self.server_udp_port = udp_port

        self.setWindowTitle(f"VimCord — {username}")
        self.user_panel.set_user(username, user_id)
        self.channel_list.set_my_user_id(user_id)

        # Cache rooms
        self.rooms = {r["room_id"]: r for r in rooms}
        self.users = {u["user_id"]: u for u in users}

        # Populate UI
        self.server_nav.set_rooms(list(self.rooms.values()))
        self.channel_list.show_dm_mode(list(self.users.values()))

        # Start audio and UDP
        self.audio_manager.start()
        self.udp_voice.start(user_id, host, udp_port)

        # Default select the first room if available
        default_r = next((r for r in self.rooms.values() if r["room_id"] == "room-default"), None)
        if default_r:
            self._on_room_nav_selected(default_r["room_id"])
            self.server_nav.set_active(default_r["room_id"])

    # ------------------ Navigation Handlers ------------------

    def _on_dm_nav_selected(self):
        self.current_room_id = None
        self.channel_list.show_dm_mode(list(self.users.values()))
        self.chat_view.set_target("Личные сообщения", is_channel=False)

    def _on_room_nav_selected(self, room_id: str):
        self.current_room_id = room_id
        room = self.rooms.get(room_id)
        if not room:
            return
        
        self.channel_list.show_room_mode(room)
        
        # Select first text channel
        text_channels = [c for c in room.get("channels", []) if c.get("channel_type") == "text"]
        if text_channels:
            first_ch = text_channels[0]
            self._on_text_channel_selected(room_id, first_ch["channel_id"], first_ch["name"])

    def _on_create_room_prompt(self):
        name, ok = QInputDialog.getText(self, "Создать сервер", "Название нового сервера (комнаты):")
        if ok and name.strip():
            self.tcp_client.send_create_room(name.strip())

    def _on_create_channel_prompt(self, room_id: str):
        items = ["Текстовый канал", "Голосовой канал"]
        ch_type_str, ok1 = QInputDialog.getItem(self, "Создать канал", "Тип канала:", items, 0, False)
        if not ok1:
            return
        
        ch_type = "voice" if "Голосовой" in ch_type_str else "text"
        name, ok2 = QInputDialog.getText(self, "Создать канал", "Название канала:")
        if ok2 and name.strip():
            self.tcp_client.send_create_channel(room_id, name.strip(), ch_type)

    def _on_delete_room(self, room_id: str):
        self.tcp_client.send_delete_room(room_id)

    # ------------------ Channel / DM Selection ------------------

    def _on_text_channel_selected(self, room_id: str, channel_id: str, name: str):
        self.current_text_channel_id = channel_id
        self.current_dm_peer_id = None
        self.chat_view.set_target(name, is_channel=True)

    def _on_voice_channel_selected(self, room_id: str, channel_id: str, name: str):
        # Disconnect any active 1-on-1 call first
        if self.active_call_id:
            self._on_end_active_call()

        self.current_voice_channel_id = channel_id
        self.udp_voice.current_channel_id = channel_id
        self.channel_list.set_active_voice(channel_id)

        # Notify server
        self.tcp_client.send_join_voice(room_id, channel_id)
        self.audio_manager.play_join_chime()

        # Update voice stage
        self.voice_view.set_channel_info(name)
        self.voice_view.show()
        self._refresh_voice_stage_users()

    def _on_disconnect_voice(self):
        if self.current_voice_channel_id:
            self.tcp_client.send_leave_voice()
            self.current_voice_channel_id = None
            self.udp_voice.current_channel_id = None
            self.channel_list.set_active_voice(None)
            self.voice_view.hide()
            self.audio_manager.play_leave_chime()
            self.audio_manager.clear_peers()

    def _on_dm_user_selected(self, user_id: str, username: str):
        self.current_dm_peer_id = user_id
        self.current_text_channel_id = None
        self.chat_view.set_target(username, is_channel=False)

    def _on_call_user_requested(self, user_id: str):
        if self.active_call_id or self.current_voice_channel_id:
            ret = QMessageBox.question(
                self, "Звонок",
                "Вы уже находитесь в голосовом канале или звонке. Переключиться на новый звонок?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if ret != QMessageBox.StandardButton.Yes:
                return
            self._on_disconnect_voice()
            if self.active_call_id:
                self._on_end_active_call()

        target = self.users.get(user_id)
        target_name = target.get("username", "пользователю") if target else "пользователю"
        self.audio_manager.start_ringtone("outgoing")
        self.tcp_client.send_call_start(user_id)

    # ------------------ Text Chat ------------------

    def _on_send_chat_message(self, text: str):
        if self.current_text_channel_id:
            self.tcp_client.send_chat_message("channel", self.current_text_channel_id, text)
        elif self.current_dm_peer_id:
            self.tcp_client.send_chat_message("dm", self.current_dm_peer_id, text)

    def _on_chat_message_received(self, msg: Dict[str, Any]):
        t_type = msg.get("target_type")
        t_id = msg.get("target_id")
        sender_id = msg.get("sender_id")

        if t_type == "channel" and t_id == self.current_text_channel_id:
            self.chat_view.append_message(msg)
        elif t_type == "dm":
            if t_id == self.current_dm_peer_id or sender_id == self.current_dm_peer_id or sender_id == self.my_user_id:
                self.chat_view.append_message(msg)

    # ------------------ 1-on-1 Direct Calls Signaling ------------------

    def _on_incoming_call(self, call_id: str, from_user_id: str, from_username: str):
        self.audio_manager.start_ringtone("incoming")
        self.incoming_dialog = IncomingCallDialog(call_id, from_user_id, from_username, self)
        self.incoming_dialog.accepted_signal.connect(self._on_accept_incoming_call)
        self.incoming_dialog.declined_signal.connect(self._on_decline_incoming_call)
        self.incoming_dialog.show()

    def _on_accept_incoming_call(self, call_id: str):
        self.audio_manager.stop_ringtone()
        self._on_disconnect_voice()  # Leave any room voice channel
        self.tcp_client.send_call_accept(call_id)

    def _on_decline_incoming_call(self, call_id: str):
        self.audio_manager.stop_ringtone()
        self.tcp_client.send_call_decline(call_id)

    def _on_call_ringing(self, call_id: str, target_user_id: str):
        pass  # Ringtone already started

    def _on_call_accepted(self, call_id: str, peer_id: str, peer_name: str):
        self.audio_manager.stop_ringtone()
        self.active_call_id = call_id
        self.active_call_peer_name = peer_name
        self.udp_voice.active_call_id = call_id

        # Show call banner
        self.call_banner.start(peer_name)

        # Show voice view with participants
        self.voice_view.set_channel_info(f"Личный звонок: {peer_name}")
        self.voice_view.update_participants([
            {"user_id": self.my_user_id, "username": self.my_username},
            {"user_id": peer_id, "username": peer_name}
        ])
        self.voice_view.show()

    def _on_call_declined(self, call_id: str):
        self.audio_manager.stop_ringtone()
        QMessageBox.information(self, "Звонок отклонен", "Собеседник отклонил вызов.")

    def _on_call_ended(self, call_id: str):
        self.audio_manager.stop_ringtone()
        if self.active_call_id == call_id:
            self.active_call_id = None
            self.udp_voice.active_call_id = None
            self.call_banner.stop()
            self.voice_view.hide()
            self.audio_manager.clear_peers()

    def _on_call_failed(self, reason: str):
        self.audio_manager.stop_ringtone()
        QMessageBox.warning(self, "Ошибка вызова", reason)

    def _on_end_active_call(self):
        if self.active_call_id:
            self.tcp_client.send_call_end(self.active_call_id)
            self.active_call_id = None
            self.udp_voice.active_call_id = None
            self.call_banner.stop()
            self.voice_view.hide()
            self.audio_manager.clear_peers()

    # ------------------ Audio & Speaking Indicators ------------------

    def _on_mic_toggled(self, is_muted: bool):
        self.audio_manager.is_muted = is_muted

    def _on_deafen_toggled(self, is_deafened: bool):
        self.audio_manager.is_deafened = is_deafened

    def _on_settings_clicked(self):
        dlg = SettingsDialog(self.audio_manager, self)
        dlg.exec()

    def _on_peer_speaking(self, user_id: str, is_speaking: bool):
        self.voice_view.set_user_speaking(user_id, is_speaking)

    def _refresh_voice_stage_users(self):
        if not self.current_voice_channel_id or not self.current_room_id:
            return
        room = self.rooms.get(self.current_room_id)
        if not room:
            return
        
        participants = []
        for ch in room.get("channels", []):
            if ch.get("channel_id") == self.current_voice_channel_id:
                for uid in ch.get("voice_users", []):
                    uname = uid
                    if uid == self.my_user_id:
                        uname = self.my_username
                    elif uid in self.users:
                        uname = self.users[uid].get("username", uid)
                    participants.append({"user_id": uid, "username": uname})
                break
        self.voice_view.update_participants(participants)

    # ------------------ Server Events ------------------

    def _on_user_presence(self, user_dict: Dict[str, Any]):
        uid = user_dict.get("user_id")
        if not uid:
            return
        if user_dict.get("online", True):
            self.users[uid] = user_dict
        else:
            self.users.pop(uid, None)
        
        self.channel_list.update_users(list(self.users.values()))

    def _on_room_created(self, room: Dict[str, Any]):
        rid = room.get("room_id")
        self.rooms[rid] = room
        self.server_nav.add_room_button(room)

    def _on_room_deleted(self, room_id: str):
        self.rooms.pop(room_id, None)
        self.server_nav.remove_room_button(room_id)
        if self.current_room_id == room_id:
            self._on_dm_nav_selected()

    def _on_channel_created(self, room_id: str, channel: Dict[str, Any]):
        if room_id in self.rooms:
            self.rooms[room_id]["channels"].append(channel)
            if self.current_room_id == room_id:
                self.channel_list.show_room_mode(self.rooms[room_id])

    def _on_channel_deleted(self, room_id: str, channel_id: str):
        if room_id in self.rooms:
            self.rooms[room_id]["channels"] = [
                c for c in self.rooms[room_id]["channels"] if c.get("channel_id") != channel_id
            ]
            if self.current_room_id == room_id:
                self.channel_list.show_room_mode(self.rooms[room_id])

    def _on_voice_state_update(self, update: Dict[str, Any]):
        r_id = update.get("room_id")
        ch_id = update.get("channel_id")
        u_id = update.get("user_id")
        action = update.get("action")

        if r_id in self.rooms:
            for c in self.rooms[r_id]["channels"]:
                if c.get("channel_id") == ch_id:
                    v_users = set(c.get("voice_users", []))
                    if action == "join":
                        v_users.add(u_id)
                    elif action == "leave":
                        v_users.discard(u_id)
                    c["voice_users"] = list(v_users)
                    break
            
            if self.current_room_id == r_id:
                self.channel_list.show_room_mode(self.rooms[r_id])
                if self.current_voice_channel_id == ch_id:
                    self._refresh_voice_stage_users()

    def _on_server_disconnected(self):
        self.voice_view.hide()
        self.call_banner.stop()
        self.audio_manager.stop()
        self.udp_voice.stop()
        QMessageBox.critical(self, "Разрыв связи", "Соединение с сервером VimCord потеряно.")

    def closeEvent(self, event):
        if self.active_call_id:
            self.tcp_client.send_call_end(self.active_call_id)
        if self.current_voice_channel_id:
            self.tcp_client.send_leave_voice()
        self.tcp_client.disconnect()
        self.audio_manager.stop()
        self.udp_voice.stop()
        super().closeEvent(event)
