"""
Main Window for VimCord.
Coordinates Navigation Rail, Channels/Friends sidebar, Text Chat with history,
Voice Stage with animated VAD & Screen Sharing, and Account Settings.
"""

import logging
from typing import Dict, Any, List, Optional
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QSplitter,
    QInputDialog, QMessageBox, QStackedWidget, QApplication
)

from vimcord.client.audio.audio_manager import AudioManager
from vimcord.client.network.tcp_client import TCPClient
from vimcord.client.network.udp_voice import UDPVoiceClient
from vimcord.client.video.screen_share import ScreenCapturer
from vimcord.client.ui.server_nav import ServerNavBar
from vimcord.client.ui.channel_list import ChannelListWidget
from vimcord.client.ui.user_panel import UserPanel
from vimcord.client.ui.voice_bar import VoiceConnectedBar
from vimcord.client.ui.voice_view import VoiceView
from vimcord.client.ui.chat_view import ChatView
from vimcord.client.ui.friends_view import FriendsView
from vimcord.client.ui.call_overlay import IncomingCallDialog, ActiveCallBanner
from vimcord.client.ui.settings_dialog import SettingsDialog
from vimcord.client.ui.profile_modal import UserProfileModal
from vimcord.client.ui.screen_window import ScreenShareWindow
from vimcord.client.ui.toast_notification import ToastNotification

logger = logging.getLogger("VimCord.MainWindow")


class MainWindow(QMainWindow):
    def __init__(self, tcp_client: TCPClient, audio_manager: AudioManager, udp_voice: UDPVoiceClient):
        super().__init__()
        self.tcp_client = tcp_client
        self.audio_manager = audio_manager
        self.udp_voice = udp_voice

        # Screen capturer
        self.screen_capturer = ScreenCapturer(send_func=self.udp_voice.send_screen_packet)
        self.screen_share_window = ScreenShareWindow()

        # User profile state
        self.my_user_id = ""
        self.my_username = ""
        self.my_avatar_color = "#5865F2"
        self.my_avatar_image = ""
        self.my_status_text = "В сети"
        self.server_host = "127.0.0.1"
        self.server_udp_port = 9989

        # Cache of rooms and users
        self.rooms: Dict[str, Dict[str, Any]] = {}
        self.users: Dict[str, Dict[str, Any]] = {}
        self.friends: List[Dict[str, Any]] = []

        self.current_room_id: Optional[str] = None  # None = @me (DMs)
        self.current_text_channel_id: Optional[str] = None
        self.current_dm_peer_id: Optional[str] = None
        self.current_voice_channel_id: Optional[str] = None

        # Call state
        self.incoming_dialog: Optional[IncomingCallDialog] = None
        self.active_call_id: Optional[str] = None
        self.active_call_peer_name: str = ""

        self.toast = ToastNotification(self)

        self.setWindowTitle("VimCord")
        self.resize(1120, 740)
        self.setMinimumSize(880, 560)

        self._init_ui()
        self._bind_signals()

    def _init_ui(self):
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)

        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 1. Leftmost server navigation rail (72px)
        self.server_nav = ServerNavBar(self)
        main_layout.addWidget(self.server_nav)

        # 2. Sidebar container (240px)
        sidebar_container = QWidget()
        sidebar_container.setFixedWidth(240)
        sidebar_container.setStyleSheet("background-color: #2b2d31;")
        sidebar_layout = QVBoxLayout(sidebar_container)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(0)

        self.channel_list = ChannelListWidget(sidebar_container)
        sidebar_layout.addWidget(self.channel_list, 1)

        # Compact Voice Connected Bar above UserPanel
        self.voice_bar = VoiceConnectedBar(sidebar_container)
        self.voice_bar.hide()
        sidebar_layout.addWidget(self.voice_bar)

        self.user_panel = UserPanel(sidebar_container)
        sidebar_layout.addWidget(self.user_panel)

        main_layout.addWidget(sidebar_container)

        # 3. Main Center Area (Stacked Widget)
        self.main_stack = QStackedWidget(self)

        # View 0: Friends View (when clicking "Друзья" in DMs)
        self.friends_view = FriendsView(self.main_stack)
        self.main_stack.addWidget(self.friends_view)

        # View 1: Chat View (100% full height, no awkward splitter)
        chat_container = QWidget()
        c_layout = QVBoxLayout(chat_container)
        c_layout.setContentsMargins(0, 0, 0, 0)
        c_layout.setSpacing(0)

        self.call_banner = ActiveCallBanner(chat_container)
        self.call_banner.hide()
        c_layout.addWidget(self.call_banner)

        self.chat_view = ChatView(chat_container)
        c_layout.addWidget(self.chat_view, 1)
        self.main_stack.addWidget(chat_container)

        # View 2: Voice Stage View (Full stage when viewing voice channel)
        voice_container = QWidget()
        v_layout = QVBoxLayout(voice_container)
        v_layout.setContentsMargins(0, 0, 0, 0)
        v_layout.setSpacing(0)

        self.voice_view = VoiceView(voice_container)
        v_layout.addWidget(self.voice_view, 1)
        self.main_stack.addWidget(voice_container)

        main_layout.addWidget(self.main_stack, 1)

    def _bind_signals(self):
        # Server Nav
        self.server_nav.dm_selected.connect(self._on_dm_nav_selected)
        self.server_nav.room_selected.connect(self._on_room_nav_selected)
        self.server_nav.create_room_requested.connect(self._on_server_add_or_join_prompt)

        # Channel List
        self.channel_list.friends_tab_selected.connect(self._on_friends_tab_selected)
        self.channel_list.text_channel_selected.connect(self._on_text_channel_selected)
        self.channel_list.voice_channel_selected.connect(self._on_voice_channel_selected)
        self.channel_list.create_channel_requested.connect(self._on_create_channel_prompt)
        self.channel_list.delete_room_requested.connect(self._on_delete_room)
        self.channel_list.invite_room_requested.connect(self._on_create_room_invite)
        self.channel_list.dm_user_selected.connect(self._on_dm_user_selected)
        self.channel_list.call_user_requested.connect(self._on_call_user_requested)

        # Friends View
        self.friends_view.open_dm_chat.connect(self._on_dm_user_selected)
        self.friends_view.start_call.connect(self._on_call_user_requested)
        self.friends_view.send_friend_req.connect(lambda uname: self.tcp_client.send_friend_request(uname))
        self.friends_view.accept_friend_req.connect(lambda uid: self.tcp_client.send_accept_friend_request(uid))
        self.friends_view.decline_friend_req.connect(lambda uid: self.tcp_client.send_decline_friend_request(uid))

        # Voice Connected Bar
        self.voice_bar.disconnect_clicked.connect(self._on_disconnect_voice)
        self.voice_bar.screen_share_clicked.connect(lambda: self._on_screen_share_toggled(None))
        self.voice_bar.channel_clicked.connect(self._on_voice_bar_channel_clicked)

        # Profile modal triggers
        self.channel_list.user_profile_requested.connect(self._open_user_profile)
        self.voice_view.user_profile_requested.connect(self._open_user_profile)
        self.user_panel.profile_clicked.connect(self._open_my_profile)

        # Screen Share window
        self.screen_share_window.stop_stream_requested.connect(lambda: self._on_screen_share_toggled(False))
        self.screen_capturer.frame_captured.connect(self._on_local_screen_frame)

        # Toast notification
        self.toast.clicked.connect(self._on_toast_clicked)

        # User Panel
        self.user_panel.mic_toggled.connect(self._on_mic_toggled)
        self.user_panel.deafen_toggled.connect(self._on_deafen_toggled)
        self.user_panel.settings_clicked.connect(self._on_settings_clicked)

        # Voice View & Screen Share
        self.voice_view.disconnect_clicked.connect(self._on_disconnect_voice)
        self.voice_view.screen_share_toggled.connect(self._on_screen_share_toggled)
        self.call_banner.end_call_clicked.connect(self._on_end_active_call)

        # Chat View
        self.chat_view.send_message_requested.connect(self._on_send_chat_message)

        # TCP Client events
        self.tcp_client.signals.disconnected.connect(self._on_server_disconnected)
        self.tcp_client.signals.user_presence.connect(self._on_user_presence)
        self.tcp_client.signals.room_created.connect(self._on_room_created)
        self.tcp_client.signals.room_deleted.connect(self._on_room_deleted)
        self.tcp_client.signals.channel_created.connect(self._on_channel_created)
        self.tcp_client.signals.channel_deleted.connect(self._on_channel_deleted)
        self.tcp_client.signals.voice_state_update.connect(self._on_voice_state_update)
        self.tcp_client.signals.chat_message.connect(self._on_chat_message_received)
        self.tcp_client.signals.history_response.connect(self._on_history_received)
        self.tcp_client.signals.friends_update.connect(self._on_friends_update)
        self.tcp_client.signals.friend_request_resp.connect(self._on_friend_request_resp)
        self.tcp_client.signals.room_invite_created.connect(self._on_room_invite_created)
        self.tcp_client.signals.room_invite_joined.connect(self._on_room_invite_joined)
        self.tcp_client.signals.profile_update_resp.connect(self._on_profile_update_resp)
        self.tcp_client.signals.user_media_state.connect(self._on_user_media_state)
        self.tcp_client.signals.change_password_resp.connect(self._on_change_password_resp)

        # 1-on-1 Direct Calls
        self.tcp_client.signals.incoming_call.connect(self._on_incoming_call)
        self.tcp_client.signals.call_ringing.connect(self._on_call_ringing)
        self.tcp_client.signals.call_accepted.connect(self._on_call_accepted)
        self.tcp_client.signals.call_declined.connect(self._on_call_declined)
        self.tcp_client.signals.call_ended.connect(self._on_call_ended)
        self.tcp_client.signals.call_failed.connect(self._on_call_failed)

        # UDP Audio & Screen
        self.udp_voice.signals.peer_speaking.connect(self._on_peer_speaking)
        self.udp_voice.signals.screen_frame_received.connect(self._on_screen_frame_received)

    def initialize_session(self, user_id: str, username: str, avatar_color: str, status_text: str,
                           rooms: List[Dict], users: List[Dict], friends: List[Dict], host: str, udp_port: int, avatar_image: str = ""):
        self.my_user_id = user_id
        self.my_username = username
        self.my_avatar_color = avatar_color or "#5865F2"
        self.my_avatar_image = avatar_image or ""
        self.my_status_text = status_text or "В сети"
        self.server_host = host
        self.server_udp_port = udp_port

        self.setWindowTitle(f"VimCord — {username}")
        self.user_panel.set_user(username, user_id, self.my_avatar_color, self.my_status_text, self.my_avatar_image)
        self.channel_list.set_my_user_id(user_id)

        self.rooms = {r["room_id"]: r for r in rooms}
        self.users = {u["user_id"]: u for u in users}
        self.friends = friends

        self.server_nav.set_rooms(list(self.rooms.values()))
        self.channel_list.set_friends(friends)
        self.channel_list.show_dm_mode(list(self.users.values()))
        self.friends_view.set_friends(friends)
        self.friends_view.set_online_users(self.users)

        self.audio_manager.start()
        self.udp_voice.start(user_id, host, udp_port)

        # Open default server or friends tab
        default_r = next((r for r in self.rooms.values() if r["room_id"] == "room-default"), None)
        if default_r:
            self._on_room_nav_selected(default_r["room_id"])
            self.server_nav.set_active(default_r["room_id"])
        else:
            self._on_friends_tab_selected()

    # ------------------ Navigation Handlers ------------------

    def _on_dm_nav_selected(self):
        self.current_room_id = None
        self.channel_list.show_dm_mode(list(self.users.values()))
        self._on_friends_tab_selected()

    def _on_friends_tab_selected(self):
        self.main_stack.setCurrentWidget(self.friends_view)
        self.friends_view.set_friends(self.friends)
        self.friends_view.set_online_users(self.users)

    def _on_room_nav_selected(self, room_id: str):
        self.current_room_id = room_id
        room = self.rooms.get(room_id)
        if not room:
            return
        
        self.channel_list.show_room_mode(room)
        self.main_stack.setCurrentIndex(1)  # Chat & Voice Splitter
        
        text_channels = [c for c in room.get("channels", []) if c.get("channel_type") == "text"]
        if text_channels:
            first_ch = text_channels[0]
            self._on_text_channel_selected(room_id, first_ch["channel_id"], first_ch["name"])

    def _on_server_add_or_join_prompt(self):
        items = ["Создать новый сервер (комнату)", "Присоединиться по инвайт-коду"]
        choice, ok = QInputDialog.getItem(self, "Серверы VimCord", "Выберите действие:", items, 0, False)
        if not ok:
            return

        if "Создать" in choice:
            name, ok2 = QInputDialog.getText(self, "Создать сервер", "Название нового сервера:")
            if ok2 and name.strip():
                self.tcp_client.send_create_room(name.strip())
        else:
            code, ok2 = QInputDialog.getText(self, "Присоединиться к серверу", "Введите код приглашения (например, VC-A1B2):")
            if ok2 and code.strip():
                self.tcp_client.send_join_room_by_invite(code.strip())

    def _on_create_room_invite(self, room_id: str):
        self.tcp_client.send_create_room_invite(room_id)

    def _on_room_invite_created(self, room_id: str, code: str):
        # Copy to clipboard and show info
        clipboard = QApplication.clipboard()
        clipboard.setText(code)
        QMessageBox.information(
            self, "Приглашение на сервер",
            f"Код приглашения создан и скопирован в буфер обмена!\n\nКод: {code}\n\nОтправьте его друзьям, чтобы они присоединились к серверу."
        )

    def _on_room_invite_joined(self, success: bool, data: Dict[str, Any]):
        if success:
            room = data.get("room", {})
            rid = room.get("room_id")
            if rid:
                self.rooms[rid] = room
                self.server_nav.add_room_button(room)
                self._on_room_nav_selected(rid)
                self.server_nav.set_active(rid)
            QMessageBox.information(self, "Успешно", f"Вы присоединились к серверу '{room.get('name')}'!")
        else:
            QMessageBox.warning(self, "Ошибка", data.get("message", "Не удалось присоединиться по коду"))

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
        self.main_stack.setCurrentIndex(1)
        self.chat_view.set_target(channel_id, name, is_channel=True)
        # Request persistent history from server
        self.tcp_client.send_get_history("channel", channel_id)

    def _on_voice_channel_selected(self, room_id: str, channel_id: str, name: str):
        if self.active_call_id:
            self._on_end_active_call()

        self.current_voice_channel_id = channel_id
        self.udp_voice.current_channel_id = channel_id
        self.channel_list.set_active_voice(channel_id)

        self.tcp_client.send_join_voice(room_id, channel_id)
        self.audio_manager.play_join_chime()

        # Update VoiceConnectedBar in sidebar
        room_name = self.rooms.get(room_id, {}).get("name", "")
        self.voice_bar.set_channel(room_name, name)
        self.voice_bar.show()

        # Update voice stage
        self.voice_view.set_channel_info(name)
        self._refresh_voice_stage_users()
        self.main_stack.setCurrentIndex(2)

    def _on_voice_bar_channel_clicked(self):
        if self.current_voice_channel_id:
            self.main_stack.setCurrentIndex(2)

    def _on_disconnect_voice(self):
        if self.screen_capturer.is_sharing:
            self.screen_capturer.stop_sharing()
            self.voice_bar.set_screen_sharing(False)
            self.screen_share_window.hide()

        if self.current_voice_channel_id:
            self.tcp_client.send_leave_voice()
            self.current_voice_channel_id = None
            self.udp_voice.current_channel_id = None
            self.channel_list.set_active_voice(None)
            self.voice_bar.hide()
            self.voice_view.hide_screen_share()
            self.audio_manager.play_leave_chime()
            self.audio_manager.clear_peers()
            if self.main_stack.currentIndex() == 2:
                if self.current_room_id:
                    self.main_stack.setCurrentIndex(1)
                else:
                    self.main_stack.setCurrentIndex(0)

    def _on_dm_user_selected(self, user_id: str, username: str):
        self.current_dm_peer_id = user_id
        self.current_text_channel_id = None
        self.main_stack.setCurrentIndex(1)
        self.chat_view.set_target(user_id, username, is_channel=False)
        # Request persistent history from server
        self.tcp_client.send_get_history("dm", user_id)

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

        if t_type == "channel":
            self.chat_view.append_message(msg)
        elif t_type == "dm":
            dm_peer = sender_id if sender_id != self.my_user_id else t_id
            msg_copy = dict(msg)
            msg_copy["target_id"] = dm_peer
            self.chat_view.append_message(msg_copy)

        # Show notification toast if chat is not in focus
        is_focused = False
        if self.main_stack.currentIndex() == 1:
            if t_type == "channel" and self.current_text_channel_id == t_id:
                is_focused = True
            elif t_type == "dm" and (self.current_dm_peer_id == sender_id or self.current_dm_peer_id == t_id):
                is_focused = True

        if sender_id != self.my_user_id and not is_focused:
            s_name = msg.get("sender_name", "Пользователь")
            content = msg.get("content", "")
            self.toast.show_toast(
                title=f"Сообщение от {s_name}",
                message=content,
                icon="💬",
                payload={"type": "chat", "msg": msg}
            )

    def _on_toast_clicked(self, payload: Any):
        if not payload or not isinstance(payload, dict):
            return
        if payload.get("type") == "chat":
            msg = payload.get("msg", {})
            ttype = msg.get("target_type")
            tid = msg.get("target_id")
            sname = msg.get("sender_name", "")
            sid = msg.get("sender_id", "")
            if ttype == "channel":
                for r in self.rooms.values():
                    for c in r.get("channels", []):
                        if c.get("channel_id") == tid:
                            self._on_room_nav_selected(r["room_id"])
                            self._on_text_channel_selected(r["room_id"], tid, c.get("name", "канал"))
                            return
            elif ttype == "dm":
                target_uid = sid if sid != self.my_user_id else tid
                self._on_dm_user_selected(target_uid, sname)

    def _on_history_received(self, target_type: str, target_id: str, messages: List[Dict[str, Any]]):
        self.chat_view.set_history(target_id, messages)

    # ------------------ Screen Sharing ------------------

    def _on_screen_share_toggled(self, is_sharing: Optional[bool] = None):
        target = self.active_call_id or self.current_voice_channel_id
        if not target:
            QMessageBox.information(self, "Демонстрация экрана", "Подключитесь к голосовому каналу или звонку, чтобы включить демонстрацию экрана.")
            return

        if is_sharing is None:
            new_sharing = not self.screen_capturer.is_sharing
        else:
            new_sharing = is_sharing

        if new_sharing:
            self.screen_capturer.start_sharing(self.my_user_id, target)
            self.voice_bar.set_screen_sharing(True)
            self.voice_view.screen_btn.setText("🔴 Остановить экран")
            self.screen_share_window.set_streamer(self.my_username, is_local=True)
            self.screen_share_window.show()
        else:
            self.screen_capturer.stop_sharing()
            self.voice_bar.set_screen_sharing(False)
            self.voice_view.screen_btn.setText("🖥️ Экран")
            self.screen_share_window.hide()

    def _on_local_screen_frame(self, jpeg_data: bytes):
        pixmap = QPixmap()
        if pixmap.loadFromData(jpeg_data, "JPEG"):
            self.screen_share_window.set_streamer(self.my_username, is_local=True)
            self.screen_share_window.update_frame(pixmap)
            self.voice_view.display_screen_frame(self.my_username, jpeg_data)

    def _on_screen_frame_received(self, sender_id: str, jpeg_data: bytes):
        sender_name = sender_id
        if sender_id in self.users:
            sender_name = self.users[sender_id].get("username", sender_id)
        pixmap = QPixmap()
        if pixmap.loadFromData(jpeg_data, "JPEG"):
            self.screen_share_window.set_streamer(sender_name, is_local=False)
            self.screen_share_window.update_frame(pixmap)
            if not self.screen_share_window.isVisible():
                self.screen_share_window.show()
        self.voice_view.display_screen_frame(sender_name, jpeg_data)

    # ------------------ Direct Calls (1-on-1) ------------------

    def _on_incoming_call(self, call_id: str, from_user_id: str, from_username: str):
        self.audio_manager.start_ringtone("incoming")
        self.incoming_dialog = IncomingCallDialog(call_id, from_user_id, from_username, self)
        self.incoming_dialog.accepted_signal.connect(self._on_accept_incoming_call)
        self.incoming_dialog.declined_signal.connect(self._on_decline_incoming_call)
        self.incoming_dialog.show()

    def _on_accept_incoming_call(self, call_id: str):
        self.audio_manager.stop_ringtone()
        self._on_disconnect_voice()
        self.tcp_client.send_call_accept(call_id)

    def _on_decline_incoming_call(self, call_id: str):
        self.audio_manager.stop_ringtone()
        self.tcp_client.send_call_decline(call_id)

    def _on_call_ringing(self, call_id: str, target_user_id: str):
        pass

    def _on_call_accepted(self, call_id: str, peer_id: str, peer_name: str):
        self.audio_manager.stop_ringtone()
        self.active_call_id = call_id
        self.active_call_peer_name = peer_name
        self.udp_voice.active_call_id = call_id

        self.call_banner.start(peer_name)
        self.main_stack.setCurrentIndex(1)

        peer_color = "#5865F2"
        if peer_id in self.users:
            peer_color = self.users[peer_id].get("avatar_color", "#5865F2")

        self.voice_view.set_channel_info(f"Личный звонок: {peer_name}")
        self.voice_view.update_participants([
            {"user_id": self.my_user_id, "username": self.my_username, "avatar_color": self.my_avatar_color},
            {"user_id": peer_id, "username": peer_name, "avatar_color": peer_color}
        ])
        self.voice_view.show()

    def _on_call_declined(self, call_id: str):
        self.audio_manager.stop_ringtone()
        QMessageBox.information(self, "Звонок отклонен", "Собеседник отклонил вызов.")

    def _on_call_ended(self, call_id: str):
        self.audio_manager.stop_ringtone()
        if self.active_call_id == call_id:
            if self.screen_capturer.is_sharing:
                self.screen_capturer.stop_sharing()
            self.active_call_id = None
            self.udp_voice.active_call_id = None
            self.call_banner.stop()
            self.voice_view.hide_screen_share()
            self.voice_view.hide()
            self.audio_manager.clear_peers()

    def _on_call_failed(self, reason: str):
        self.audio_manager.stop_ringtone()
        QMessageBox.warning(self, "Ошибка вызова", reason)

    def _on_end_active_call(self):
        if self.active_call_id:
            self.tcp_client.send_call_end(self.active_call_id)
            if self.screen_capturer.is_sharing:
                self.screen_capturer.stop_sharing()
            self.active_call_id = None
            self.udp_voice.active_call_id = None
            self.call_banner.stop()
            self.voice_view.hide_screen_share()
            self.voice_view.hide()
            self.audio_manager.clear_peers()

    # ------------------ Audio & Indicators ------------------

    def _on_mic_toggled(self, is_muted: bool):
        self.audio_manager.is_muted = is_muted
        self.tcp_client.send_user_media_state(is_muted, self.user_panel.is_deafened)

    def _on_deafen_toggled(self, is_deafened: bool):
        self.audio_manager.is_deafened = is_deafened
        self.tcp_client.send_user_media_state(self.user_panel.is_muted, is_deafened)

    def _on_user_media_state(self, update: Dict[str, Any]):
        uid = update.get("user_id")
        is_muted = update.get("is_muted", False)
        is_deaf = update.get("is_deafened", False)
        if uid in self.users:
            self.users[uid]["is_muted"] = is_muted
            self.users[uid]["is_deafened"] = is_deaf
        self.voice_view.set_user_media_state(uid, is_muted, is_deaf)
        if self.current_room_id and self.current_room_id in self.rooms:
            self.channel_list.show_room_mode(self.rooms[self.current_room_id])

    def _on_settings_clicked(self):
        user_data = {
            "user_id": self.my_user_id,
            "username": self.my_username,
            "avatar_color": self.my_avatar_color,
            "avatar_image": getattr(self, "my_avatar_image", ""),
            "status_text": self.my_status_text
        }
        dlg = SettingsDialog(self.audio_manager, user_data, self)
        dlg.profile_updated.connect(lambda u, s, c, img: self.tcp_client.send_update_profile(u, s, c, img))
        dlg.password_changed.connect(lambda op, np: self.tcp_client.send_change_password(op, np))
        dlg.logout_requested.connect(self._on_logout_requested)
        dlg.exec()

    def _open_user_profile(self, user_dict: Dict[str, Any]):
        uid = user_dict.get("user_id")
        if not uid:
            return
        is_self = (uid == self.my_user_id)
        is_friend = any(f.get("peer_id") == uid and f.get("friendship_status") == "accepted" for f in self.friends)

        full_info = dict(user_dict)
        if uid in self.users:
            full_info.update(self.users[uid])
        if is_self:
            full_info["username"] = self.my_username
            full_info["avatar_color"] = self.my_avatar_color
            full_info["avatar_image"] = getattr(self, "my_avatar_image", "")
            full_info["status_text"] = self.my_status_text

        dlg = UserProfileModal(full_info, is_self=is_self, is_friend=is_friend, parent=self)
        dlg.open_dm_clicked.connect(self._on_dm_user_selected)
        dlg.start_call_clicked.connect(self._on_call_user_requested)
        dlg.add_friend_clicked.connect(lambda uname: self.tcp_client.send_friend_request(uname))
        dlg.exec()

    def _open_my_profile(self):
        self._open_user_profile({"user_id": self.my_user_id, "username": self.my_username})

    def _on_logout_requested(self):
        self.close()

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
                    color = "#5865F2"
                    img = ""
                    is_muted = False
                    is_deaf = False
                    if uid == self.my_user_id:
                        uname = self.my_username
                        color = self.my_avatar_color
                        img = getattr(self, "my_avatar_image", "")
                        is_muted = self.user_panel.is_muted
                        is_deaf = self.user_panel.is_deafened
                    elif uid in self.users:
                        u = self.users[uid]
                        uname = u.get("username", uid)
                        color = u.get("avatar_color", "#5865F2")
                        img = u.get("avatar_image", "")
                        is_muted = u.get("is_muted", False)
                        is_deaf = u.get("is_deafened", False)
                    participants.append({
                        "user_id": uid,
                        "username": uname,
                        "avatar_color": color,
                        "avatar_image": img,
                        "is_muted": is_muted,
                        "is_deafened": is_deaf
                    })
                break
        self.voice_view.update_participants(participants)

    # ------------------ Server Events ------------------

    def _on_friends_update(self, friends_list: List[Dict[str, Any]]):
        # Notify about incoming friend requests
        old_incoming = {f["peer_id"] for f in self.friends if f.get("is_incoming")}
        for f in friends_list:
            if f.get("is_incoming") and f["peer_id"] not in old_incoming:
                self.toast.show_toast(
                    title="Заявка в друзья",
                    message=f"Пользователь {f.get('username')} отправил вам заявку!",
                    icon="👥"
                )

        self.friends = friends_list
        self.channel_list.set_friends(friends_list)
        self.friends_view.set_friends(friends_list)

    def _on_friend_request_resp(self, success: bool, message: str):
        self.friends_view.set_feedback(success, message)

    def _on_profile_update_resp(self, success: bool, message: str, user_dict: Dict[str, Any]):
        if success and user_dict:
            self.my_username = user_dict.get("username", self.my_username)
            self.my_avatar_color = user_dict.get("avatar_color", self.my_avatar_color)
            self.my_avatar_image = user_dict.get("avatar_image", getattr(self, "my_avatar_image", ""))
            self.my_status_text = user_dict.get("status_text", self.my_status_text)
            self.user_panel.set_user(self.my_username, self.my_user_id, self.my_avatar_color, self.my_status_text, self.my_avatar_image)
            self.setWindowTitle(f"VimCord — {self.my_username}")

    def _on_change_password_resp(self, success: bool, message: str):
        if success:
            QMessageBox.information(self, "Пароль", message)
        else:
            QMessageBox.warning(self, "Пароль", message)

    def _on_user_presence(self, user_dict: Dict[str, Any]):
        uid = user_dict.get("user_id")
        if not uid:
            return
        if user_dict.get("online", True):
            self.users[uid] = user_dict
        else:
            self.users.pop(uid, None)
        
        self.channel_list.update_users(list(self.users.values()))
        self.friends_view.set_online_users(self.users)

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

        # Update media states if provided
        if u_id in self.users:
            if "is_muted" in update:
                self.users[u_id]["is_muted"] = update["is_muted"]
            if "is_deafened" in update:
                self.users[u_id]["is_deafened"] = update["is_deafened"]

        # Prevent ghosting: remove u_id from ALL other voice channels across all rooms on join
        if action == "join":
            for r in self.rooms.values():
                for c in r.get("channels", []):
                    if c.get("channel_id") != ch_id and "voice_users" in c:
                        if u_id in c["voice_users"]:
                            c["voice_users"].remove(u_id)

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
            if self.current_voice_channel_id:
                self._refresh_voice_stage_users()

        # If we were disconnected/left
        if u_id == self.my_user_id and action == "leave" and self.current_voice_channel_id == ch_id:
            self.current_voice_channel_id = None
            self.udp_voice.current_channel_id = None
            self.channel_list.set_active_voice(None)
            self.voice_bar.hide()
            self.voice_view.hide_screen_share()
            self.audio_manager.clear_peers()

    def _on_server_disconnected(self):
        self.voice_bar.hide()
        self.voice_view.hide()
        self.call_banner.stop()
        self.audio_manager.stop()
        self.udp_voice.stop()
        QMessageBox.critical(self, "Разрыв связи", "Соединение с сервером VimCord потеряно.")

    def closeEvent(self, event):
        if self.screen_capturer.is_sharing:
            self.screen_capturer.stop_sharing()
        if self.active_call_id:
            self.tcp_client.send_call_end(self.active_call_id)
        if self.current_voice_channel_id:
            self.tcp_client.send_leave_voice()
        self.tcp_client.disconnect()
        self.audio_manager.stop()
        self.udp_voice.stop()
        super().closeEvent(event)
