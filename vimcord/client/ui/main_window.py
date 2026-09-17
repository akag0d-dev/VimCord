"""
Main Window for VimCord.
Coordinates Navigation Rail, Channels/Friends sidebar, Text Chat with history,
Voice Stage with animated VAD & Screen Sharing, and Account Settings.
"""

import logging
import time
import uuid
from typing import Dict, Any, List, Optional
from pathlib import Path
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QPixmap, QIcon, QColor, QPainter
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QSplitter,
    QInputDialog, QMessageBox, QStackedWidget, QApplication,
    QSystemTrayIcon, QMenu, QLabel, QPushButton
)

from vimcord.common.protocol import pack_udp_audio, UDP_TYPE_SCREEN_FRAME

from vimcord.client.config import load_config, save_config
from vimcord.client.i18n import t, set_language
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
from vimcord.client.ui.toast_notification import ToastNotification, show_windows_toast
from vimcord.client.ui.member_list import MemberListWidget

logger = logging.getLogger("VimCord.MainWindow")


class ConnectionLostOverlay(QWidget):
    reconnect_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("connection_lost_overlay")
        self.setStyleSheet("""
            QWidget#connection_lost_overlay {
                background-color: rgba(18, 19, 22, 0.96);
            }
        """)
        self.countdown_seconds = 10
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._on_tick)

        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(14)

        icon_lbl = QLabel("🔌")
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setStyleSheet("font-size: 56px; margin-bottom: 4px; background: transparent;")
        layout.addWidget(icon_lbl)

        self.title_lbl = QLabel(t("connection_lost"))
        self.title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_lbl.setStyleSheet("color: #f23f43; font-size: 26px; font-weight: bold; background: transparent;")
        layout.addWidget(self.title_lbl)

        self.desc_lbl = QLabel(t("disconnected_from_server"))
        self.desc_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.desc_lbl.setStyleSheet("color: #dbdee1; font-size: 14px; background: transparent;")
        layout.addWidget(self.desc_lbl)

        self.countdown_lbl = QLabel("Automatically reconnecting in 10s...")
        self.countdown_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.countdown_lbl.setStyleSheet("color: #949ba4; font-size: 13px; background: transparent;")
        layout.addWidget(self.countdown_lbl)

        self.reconnect_btn = QPushButton(f"🔄 {t('reconnect_now')}")
        self.reconnect_btn.setFixedSize(190, 42)
        self.reconnect_btn.setStyleSheet("""
            QPushButton {
                background-color: #5865F2; color: #ffffff; font-weight: bold;
                font-size: 14px; border-radius: 6px; border: none;
            }
            QPushButton:hover { background-color: #4752c4; }
        """)
        self.reconnect_btn.clicked.connect(self._trigger_reconnect)
        layout.addWidget(self.reconnect_btn, 0, Qt.AlignmentFlag.AlignCenter)

    def show_overlay(self):
        self.countdown_seconds = 10
        self.countdown_lbl.setText("Automatically reconnecting in 10s...")
        self.reconnect_btn.setEnabled(True)
        self.reconnect_btn.setText(f"🔄 {t('reconnect_now')}")
        self.timer.start()
        if self.parent():
            self.resize(self.parent().size())
        self.show()
        self.raise_()

    def hide_overlay(self):
        self.timer.stop()
        self.hide()

    def _on_tick(self):
        self.countdown_seconds -= 1
        if self.countdown_seconds <= 0:
            self.timer.stop()
            self._trigger_reconnect()
        else:
            self.countdown_lbl.setText(f"Automatically reconnecting in {self.countdown_seconds}s...")

    def _trigger_reconnect(self):
        self.timer.stop()
        self.countdown_lbl.setText("Reconnecting to server...")
        self.reconnect_btn.setEnabled(False)
        self.reconnect_requested.emit()

    def set_reconnect_failed(self):
        self.countdown_seconds = 10
        self.countdown_lbl.setText("Reconnect failed. Retrying in 10s...")
        self.reconnect_btn.setEnabled(True)
        self.reconnect_btn.setText("🔄 Retry Now")
        self.timer.start()


class MainWindow(QMainWindow):
    def __init__(self, tcp_client: TCPClient, audio_manager: AudioManager, udp_voice: UDPVoiceClient):
        super().__init__()
        self.tcp_client = tcp_client
        self.audio_manager = audio_manager
        self.udp_voice = udp_voice

        # Screen capturer with dual reliable TCP + fast UDP transmission
        self.screen_capturer = ScreenCapturer(send_func=self.udp_voice.send_screen_packet)
        self.screen_capturer.on_frame_ready = self._send_screen_frame
        self.screen_share_window = ScreenShareWindow()
        self._last_screen_render = 0.0
        self._screen_seq = 0

        # User profile state
        self.my_user_id = ""
        self.my_username = ""
        self.my_display_name = ""
        self.my_avatar_color = "#5865F2"
        self.my_avatar_image = ""
        self.my_banner_color = "#5865F2"
        self.my_banner_image = ""
        self.my_bio = ""
        self.my_status_text = "Online"
        self.server_host = "194.226.123.199"
        self.server_tcp_port = 9988
        self.server_udp_port = 9989

        # Client Config state
        cfg = load_config()
        self.dnd_mode = cfg.get("dnd_mode", False)
        self.ptt_key = cfg.get("ptt_key", "Space")
        self.current_language = cfg.get("language", "en")
        set_language(self.current_language)

        # Push to Talk state
        self.ptt_key = "Space"

        # Ping state
        self.last_ping_time = 0.0
        self.current_ping = 0
        self.ping_timer = QTimer(self)
        self.ping_timer.setInterval(2500)
        self.ping_timer.timeout.connect(self._send_ping)

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

        self.app_icon = self._load_app_icon()
        self.setWindowIcon(self.app_icon)

        self.toast = ToastNotification(self)

        # System Tray Icon & OS Notifications
        self.tray_icon: Optional[QSystemTrayIcon] = None
        self._last_notification_payload: Any = None
        self._init_system_tray()

        self.setWindowTitle("VimCord")
        self.resize(1120, 740)
        self.setMinimumSize(880, 560)

        self._init_ui()

        # Connection Lost Overlay
        self.connection_overlay = ConnectionLostOverlay(self)
        self.connection_overlay.hide()
        self.connection_overlay.reconnect_requested.connect(self._on_reconnect_requested)

        self._bind_signals()
        self._apply_saved_theme()

    def _load_app_icon(self) -> QIcon:
        icon_path = Path(__file__).resolve().parents[3] / "icon.ico"
        if icon_path.exists():
            return QIcon(str(icon_path))
        pm = QPixmap(32, 32)
        pm.fill(QColor("#5865F2"))
        p = QPainter(pm)
        p.setPen(QColor("#FFFFFF"))
        p.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, "V")
        p.end()
        return QIcon(pm)

    def _init_system_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray_icon = QSystemTrayIcon(self.app_icon, self)
        self.tray_icon.setToolTip("VimCord")

        tray_menu = QMenu()
        restore_action = tray_menu.addAction("Open VimCord")
        restore_action.triggered.connect(self._bring_to_front)
        tray_menu.addSeparator()
        quit_action = tray_menu.addAction("Exit")
        quit_action.triggered.connect(self.close)
        self.tray_icon.setContextMenu(tray_menu)

        self.tray_icon.activated.connect(self._on_tray_activated)
        self.tray_icon.messageClicked.connect(self._on_tray_message_clicked)
        self.tray_icon.show()

    def _bring_to_front(self):
        self.showNormal()
        self.setWindowState(self.windowState() & ~Qt.WindowState.WindowMinimized | Qt.WindowState.WindowActive)
        self.raise_()
        self.activateWindow()

    def _on_tray_activated(self, reason):
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self._bring_to_front()

    def _on_tray_message_clicked(self):
        self._bring_to_front()
        if self._last_notification_payload:
            self._on_toast_clicked(self._last_notification_payload)

    def notify_user(self, title: str, message: str, icon_str: str = "💬", payload: Any = None):
        if getattr(self, "dnd_mode", False):
            return
        self._last_notification_payload = payload
        # 1. In-app toast popup
        self.toast.show_toast(
            title=title,
            message=message,
            icon=icon_str,
            payload=payload
        )
        # 2. Native OS System Notification (Windows 10/11 Action Center)
        show_windows_toast(title, message, on_click=self._bring_to_front)
        if self.tray_icon and QSystemTrayIcon.isSystemTrayAvailable():
            self.tray_icon.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, 4500)
        # 3. Audio chime
        if hasattr(self, "audio_manager") and self.audio_manager:
            self.audio_manager.play_notification_chime()

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

        # 4. Right-side Member List Sidebar (240px)
        self.member_list = MemberListWidget(self)
        self.member_list.hide()
        main_layout.addWidget(self.member_list)

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
        self.channel_list.leave_room_requested.connect(self._on_leave_room)
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
        self.chat_view.open_profile_requested.connect(lambda uid: self._open_user_profile({"user_id": uid}))

        # Screen Share window
        self.screen_share_window.stop_stream_requested.connect(lambda: self._on_screen_share_toggled(False))
        self.screen_capturer.frame_captured.connect(self._on_local_screen_frame)

        # Toast notification
        self.toast.clicked.connect(self._on_toast_clicked)

        # User Panel
        self.user_panel.mic_toggled.connect(self._on_mic_toggled)
        self.user_panel.deafen_toggled.connect(self._on_deafen_toggled)
        self.user_panel.settings_clicked.connect(self._on_settings_clicked)

        # Voice View & Member List peer volume / mute
        self.voice_view.disconnect_clicked.connect(self._on_disconnect_voice)
        self.voice_view.screen_share_toggled.connect(self._on_screen_share_toggled)
        self.voice_view.popout_stream_requested.connect(self._on_popout_stream)
        self.voice_view.stream_volume_changed.connect(self._on_stream_volume_changed)
        self.voice_view.peer_volume_changed.connect(self.audio_manager.set_peer_volume)
        self.voice_view.peer_mute_toggled.connect(self.audio_manager.set_peer_muted)
        self.call_banner.end_call_clicked.connect(self._on_end_active_call)
        self.call_banner.volume_changed.connect(self._on_call_volume_changed)

        # Member List sidebar
        self.member_list.view_profile_requested.connect(lambda uid: self._open_user_profile({"user_id": uid}))
        self.member_list.open_dm_requested.connect(self._on_dm_user_selected)
        self.member_list.call_requested.connect(self._on_call_user_requested)
        self.member_list.peer_volume_changed.connect(self.audio_manager.set_peer_volume)
        self.member_list.peer_mute_toggled.connect(self.audio_manager.set_peer_muted)

        # Chat View
        self.chat_view.send_message_requested.connect(self._on_send_chat_message)
        self.chat_view.delete_message_requested.connect(self._on_delete_chat_message)
        self.chat_view.play_voice_requested.connect(self.audio_manager.play_voice_msg)
        self.chat_view.toggle_members_requested.connect(self._toggle_member_list)

        # TCP Client events
        self.tcp_client.signals.disconnected.connect(self._on_server_disconnected)
        self.tcp_client.signals.login_response.connect(self._on_reconnect_login_resp)
        self.tcp_client.signals.user_presence.connect(self._on_user_presence)
        self.tcp_client.signals.room_created.connect(self._on_room_created)
        self.tcp_client.signals.room_deleted.connect(self._on_room_deleted)
        self.tcp_client.signals.channel_created.connect(self._on_channel_created)
        self.tcp_client.signals.channel_deleted.connect(self._on_channel_deleted)
        self.tcp_client.signals.voice_state_update.connect(self._on_voice_state_update)
        self.tcp_client.signals.chat_message.connect(self._on_chat_message_received)
        self.tcp_client.signals.message_deleted.connect(self._on_message_deleted)
        self.tcp_client.signals.history_response.connect(self._on_history_received)
        self.tcp_client.signals.friends_update.connect(self._on_friends_update)
        self.tcp_client.signals.friend_request_resp.connect(self._on_friend_request_resp)
        self.tcp_client.signals.room_invite_created.connect(self._on_room_invite_created)
        self.tcp_client.signals.room_invite_joined.connect(self._on_room_invite_joined)
        self.tcp_client.signals.leave_room_resp.connect(self._on_leave_room_resp)
        self.tcp_client.signals.room_members_resp.connect(self._on_room_members_resp)
        self.tcp_client.signals.pong.connect(self._on_pong)
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

        # Screen Sharing (TCP reliable + UDP low-latency)
        self.tcp_client.signals.screen_frame.connect(self._on_screen_frame_received)
        self.tcp_client.signals.screen_stop.connect(self._on_screen_stop_received)
        self.udp_voice.signals.screen_frame_received.connect(self._on_screen_frame_received)

        # UDP Audio
        self.udp_voice.signals.peer_speaking.connect(self._on_peer_speaking)

    def initialize_session(self, user_id: str, username: str, avatar_color: str, status_text: str,
                           rooms: List[Dict], users: List[Dict], friends: List[Dict], host: str, udp_port: int,
                           avatar_image: str = "", bio: str = "", display_name: str = "",
                           banner_color: str = "", banner_image: str = ""):
        self.my_user_id = user_id
        self.my_username = username
        self.my_display_name = display_name or username
        self.my_avatar_color = avatar_color or "#5865F2"
        self.my_avatar_image = avatar_image or ""
        self.my_banner_color = banner_color or "#5865F2"
        self.my_banner_image = banner_image or ""
        self.my_bio = bio or ""
        self.my_status_text = status_text or "Online"
        self.server_host = host
        self.server_udp_port = udp_port

        self._load_local_profile()

        self.chat_view.set_current_user_id(user_id)
        self.chat_view.set_audio_manager(self.audio_manager)
        self.voice_view.set_current_user_id(user_id)
        self.member_list.set_current_user_id(user_id)
        self.ping_timer.start()

        self.setWindowTitle(f"VimCord — {self.my_display_name} (@{self.my_username})")
        self.user_panel.set_user(self.my_username, user_id, self.my_avatar_color, self.my_status_text, self.my_avatar_image, display_name=self.my_display_name)
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
        self.member_list.hide()
        self.channel_list.show_dm_mode(list(self.users.values()))
        self._on_friends_tab_selected()

    def _on_friends_tab_selected(self):
        self.member_list.hide()
        self.main_stack.setCurrentWidget(self.friends_view)
        self.friends_view.set_friends(self.friends)
        self.friends_view.set_online_users(self.users)

    def _on_room_nav_selected(self, room_id: str):
        self.current_room_id = room_id
        room = self.rooms.get(room_id)
        if not room:
            return
        
        self.channel_list.show_room_mode(room)
        self.member_list.current_room_id = room_id
        self.member_list.show()
        self.tcp_client.send_get_room_members(room_id)
        self.main_stack.setCurrentIndex(1)  # Chat & Voice Splitter
        
        text_channels = [c for c in room.get("channels", []) if c.get("channel_type") == "text"]
        if text_channels:
            first_ch = text_channels[0]
            self._on_text_channel_selected(room_id, first_ch["channel_id"], first_ch["name"])

    def _on_server_add_or_join_prompt(self):
        items = ["Create New Server", "Join with Invite Code"]
        choice, ok = QInputDialog.getItem(self, "VimCord Servers", "Select an action:", items, 0, False)
        if not ok:
            return

        if "Create" in choice:
            name, ok2 = QInputDialog.getText(self, "Create Server", "Server name:")
            if ok2 and name.strip():
                self.tcp_client.send_create_room(name.strip())
        else:
            code, ok2 = QInputDialog.getText(self, "Join Server", "Enter invite code (e.g. VC-A1B2):")
            if ok2 and code.strip():
                self.tcp_client.send_join_room_by_invite(code.strip())

    def _on_create_room_invite(self, room_id: str):
        self.tcp_client.send_create_room_invite(room_id)

    def _on_room_invite_created(self, room_id: str, code: str):
        # Copy to clipboard and show info
        clipboard = QApplication.clipboard()
        clipboard.setText(code)
        QMessageBox.information(
            self, "Server Invite",
            f"Invite code created and copied to clipboard!\n\nCode: {code}\n\nSend it to friends so they can join."
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
            QMessageBox.information(self, "Success", f"You joined '{room.get('name')}'!")
        else:
            QMessageBox.warning(self, "Error", data.get("message", "Failed to join using invite code"))

    def _on_create_channel_prompt(self, room_id: str):
        items = ["Text Channel", "Voice Channel"]
        ch_type_str, ok1 = QInputDialog.getItem(self, "Create Channel", "Channel type:", items, 0, False)
        if not ok1:
            return
        
        ch_type = "voice" if "Voice" in ch_type_str else "text"
        name, ok2 = QInputDialog.getText(self, "Create Channel", "Channel name:")
        if ok2 and name.strip():
            self.tcp_client.send_create_channel(room_id, name.strip(), ch_type)

    def _on_delete_room(self, room_id: str):
        self.tcp_client.send_delete_room(room_id)

    # ------------------ Channel / DM Selection ------------------

    def _on_text_channel_selected(self, room_id: str, channel_id: str, name: str):
        self.current_text_channel_id = channel_id
        self.current_dm_peer_id = None
        self.member_list.show()
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
        self.voice_bar.update_ping(self.current_ping)
        self.voice_bar.show()

        # Update voice stage
        self.voice_view.set_channel_info(name)
        self.voice_view.update_connection_info(self.current_ping, self.server_host, self.server_udp_port)
        self._refresh_voice_stage_users()
        self.main_stack.setCurrentIndex(2)

    def _on_voice_bar_channel_clicked(self):
        if self.current_voice_channel_id or self.active_call_id:
            self.main_stack.setCurrentIndex(2)

    def _on_disconnect_voice(self):
        if self.screen_capturer.is_sharing:
            self.screen_capturer.stop_sharing()
            self.voice_bar.set_screen_sharing(False)
            self.screen_share_window.hide()

        if self.active_call_id:
            self._on_end_active_call()

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
        self.member_list.hide()
        self.main_stack.setCurrentIndex(1)
        self.chat_view.set_target(user_id, username, is_channel=False)
        # Request persistent history from server
        self.tcp_client.send_get_history("dm", user_id)

    def _on_call_user_requested(self, user_id: str):
        is_friend = any(f.get("peer_id") == user_id and f.get("friendship_status") == "accepted" for f in self.friends)
        if not is_friend:
            QMessageBox.warning(self, "Call Not Allowed", "You can only call users who are on your friends list.")
            return

        if self.active_call_id or self.current_voice_channel_id:
            ret = QMessageBox.question(
                self, "Call",
                "You are already in a voice channel or call. Switch to this call?",
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

    def _on_send_chat_message(self, text: str = "", image_data: str = "", voice_data: str = "", voice_duration: float = 0.0,
                              file_data: str = "", file_name: str = "", file_size: int = 0):
        target_type = "channel" if self.current_text_channel_id else "dm"
        target_id = self.current_text_channel_id if self.current_text_channel_id else self.current_dm_peer_id
        if not target_id:
            return

        msg_id = "msg-" + uuid.uuid4().hex[:12]

        self.tcp_client.send_chat_message(target_type, target_id,
                                          content=text, image_data=image_data,
                                          voice_data=voice_data, voice_duration=voice_duration,
                                          file_data=file_data, file_name=file_name, file_size=file_size,
                                          msg_id=msg_id)

        # Optimistic local append for immediate visual feedback
        local_msg = {
            "msg_id": msg_id,
            "target_type": target_type,
            "target_id": target_id,
            "sender_id": self.my_user_id,
            "sender_name": self.my_username,
            "display_name": getattr(self, "my_display_name", self.my_username),
            "avatar_color": self.my_avatar_color,
            "avatar_image": getattr(self, "my_avatar_image", ""),
            "content": text,
            "image_data": image_data,
            "voice_data": voice_data,
            "voice_duration": voice_duration,
            "file_data": file_data,
            "file_name": file_name,
            "file_size": file_size,
            "timestamp": time.time()
        }
        self.chat_view.append_message(local_msg)

    def _on_delete_chat_message(self, msg_id: str, target_type: str, target_id: str):
        self.tcp_client.send_delete_message(msg_id, target_type, target_id)

    def _on_message_deleted(self, msg_id: str, target_type: str, target_id: str):
        self.chat_view.remove_message(msg_id, target_id)

    def _toggle_member_list(self):
        if self.member_list.isVisible():
            self.member_list.hide()
        else:
            self.member_list.show()
            if self.current_room_id:
                self.tcp_client.send_get_room_members(self.current_room_id)

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

        # Play incoming message audio chime
        if sender_id != self.my_user_id:
            self.audio_manager.play_message_chime()

        # Show notification toast / system notification if chat is not in focus or window not active
        is_focused = False
        if self.main_stack.currentIndex() == 1 and self.isActiveWindow() and not self.isMinimized():
            if t_type == "channel" and self.current_text_channel_id == t_id:
                is_focused = True
            elif t_type == "dm" and (self.current_dm_peer_id == sender_id or self.current_dm_peer_id == t_id):
                is_focused = True

        if sender_id != self.my_user_id and not is_focused:
            s_name = msg.get("sender_name", "User")
            content = msg.get("content", "")
            if not content and msg.get("image_data"):
                content = "📷 [Photo]"
            elif not content and msg.get("file_name"):
                content = f"📎 [{msg.get('file_name')}]"
            elif not content and msg.get("voice_data"):
                content = "🎙️ [Voice Message]"
            self.notify_user(
                title=f"Message from {s_name}",
                message=content,
                icon_str="💬",
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
                            self._on_text_channel_selected(r["room_id"], tid, c.get("name", "channel"))
                            return
            elif ttype == "dm":
                target_uid = sid if sid != self.my_user_id else tid
                self._on_dm_user_selected(target_uid, sname)

    def _on_history_received(self, target_type: str, target_id: str, messages: List[Dict[str, Any]]):
        self.chat_view.set_history(target_id, messages)

    # ------------------ Screen Sharing ------------------

    def _on_screen_share_toggled(self, is_sharing: Optional[bool] = None):
        target = self.active_call_id or self.current_voice_channel_id
        target_type = "call" if self.active_call_id else "channel"
        if not target:
            QMessageBox.information(self, "Screen Share", "Connect to a voice channel or call first to share your screen.")
            return

        if is_sharing is None:
            new_sharing = not self.screen_capturer.is_sharing
        else:
            new_sharing = is_sharing

        if new_sharing:
            self.screen_capturer.start_sharing(self.my_user_id, target, target_type)
            self.audio_manager.start_desktop_audio_capture()
            self.voice_bar.set_screen_sharing(True)
            self.voice_view.screen_btn.setText("🔴 Stop Screen")
            self.screen_share_window.set_streamer(self.my_display_name or self.my_username, is_local=True)
            # Stream is displayed directly inside VoiceView stage - no unwanted popup window
        else:
            self.screen_capturer.stop_sharing()
            self.audio_manager.stop_desktop_audio_capture()
            self.tcp_client.send_screen_stop(target_type, target)
            self.voice_bar.set_screen_sharing(False)
            self.voice_view.screen_btn.setText("🖥️ Screen")
            self.screen_share_window.hide()
            self.voice_view.hide_screen_share()

    def _send_screen_frame(self, target_type: str, target_id: str, jpeg_data: bytes):
        # 100% UDP transmission with 1200-byte datagram chunks (Discord architecture)
        # Bypasses MTU limits without WinError 10040 and prevents TCP socket buffer choke
        self.udp_voice.send_screen_frame_chunks(target_id, jpeg_data)

    def _on_local_screen_frame(self, jpeg_data: bytes):
        if self.screen_share_window.isVisible():
            pixmap = QPixmap()
            if pixmap.loadFromData(jpeg_data, "JPEG"):
                self.screen_share_window.set_streamer(self.my_display_name or self.my_username, is_local=True)
                self.screen_share_window.update_frame(pixmap)
        self.voice_view.display_screen_frame(self.my_display_name or self.my_username, jpeg_data)

    def _on_screen_frame_received(self, sender_id: str, jpeg_data: bytes):
        now = time.time()
        # Smooth rendering up to 60 FPS (0.015s throttle)
        if now - self._last_screen_render < 0.015:
            return
        self._last_screen_render = now

        sender_name = sender_id
        if sender_id in self.users:
            sender_name = self.users[sender_id].get("display_name") or self.users[sender_id].get("username", sender_id)

        # Update separate window ONLY if it's already popped out
        if self.screen_share_window.isVisible():
            pixmap = QPixmap()
            if pixmap.loadFromData(jpeg_data, "JPEG"):
                self.screen_share_window.set_streamer(sender_name, is_local=False)
                self.screen_share_window.update_frame(pixmap)

        # Always render directly in the voice stage
        self.voice_view.display_screen_frame(sender_name, jpeg_data)

    def _on_screen_stop_received(self, sender_id: str):
        if not self.screen_capturer.is_sharing:
            self.screen_share_window.hide()
            self.voice_view.hide_screen_share()

    def _on_popout_stream(self):
        if self.screen_share_window.isVisible():
            self.screen_share_window.hide()
        else:
            self.screen_share_window.show()
            self.screen_share_window.raise_()
            self.screen_share_window.activateWindow()

    def _on_stream_volume_changed(self, vol: float):
        # Adjust streamer volume across all voice channel peers if streaming
        for uid in self.users:
            self.audio_manager.set_peer_volume(uid, vol)

    # ------------------ Direct Calls (1-on-1) ------------------

    def _on_incoming_call(self, call_id: str, from_user_id: str, from_username: str):
        self.audio_manager.start_ringtone("incoming")
        self.incoming_dialog = IncomingCallDialog(call_id, from_user_id, from_username, self)
        self.incoming_dialog.accepted_signal.connect(self._on_accept_incoming_call)
        self.incoming_dialog.declined_signal.connect(self._on_decline_incoming_call)
        self.incoming_dialog.show()
        self.notify_user(
            title="Incoming Call",
            message=f"{from_username} is calling you on VimCord!",
            icon_str="📞",
            payload={"type": "call", "call_id": call_id}
        )

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

        self.call_banner.start(peer_name, peer_id=peer_id)
        self.voice_bar.set_channel("Direct Call", peer_name)
        self.voice_bar.show()
        self.main_stack.setCurrentIndex(1)

        peer_color = "#5865F2"
        if peer_id in self.users:
            peer_color = self.users[peer_id].get("avatar_color", "#5865F2")

        self.voice_view.set_channel_info(f"Direct Call: {peer_name}")
        self.voice_view.update_participants([
            {"user_id": self.my_user_id, "username": self.my_username, "avatar_color": self.my_avatar_color},
            {"user_id": peer_id, "username": peer_name, "avatar_color": peer_color}
        ])

    def _on_call_volume_changed(self, vol: float):
        if getattr(self.call_banner, "peer_id", None):
            self.audio_manager.set_peer_volume(self.call_banner.peer_id, vol)

    def _on_call_declined(self, call_id: str):
        self.audio_manager.stop_ringtone()
        QMessageBox.information(self, "Call Declined", "Call was declined.")

    def _on_call_ended(self, call_id: str):
        self.audio_manager.stop_ringtone()
        if self.active_call_id == call_id:
            if self.screen_capturer.is_sharing:
                self.screen_capturer.stop_sharing()
            self.active_call_id = None
            self.udp_voice.active_call_id = None
            self.call_banner.stop()
            self.voice_bar.hide()
            self.voice_view.hide_screen_share()
            self.audio_manager.clear_peers()
            if self.main_stack.currentIndex() == 2:
                self.main_stack.setCurrentIndex(1)

    def _on_call_failed(self, reason: str):
        self.audio_manager.stop_ringtone()
        QMessageBox.warning(self, "Call Failed", reason)

    def _on_end_active_call(self):
        if self.active_call_id:
            self.tcp_client.send_call_end(self.active_call_id)
            if self.screen_capturer.is_sharing:
                self.screen_capturer.stop_sharing()
            self.active_call_id = None
            self.udp_voice.active_call_id = None
            self.call_banner.stop()
            self.voice_bar.hide()
            self.voice_view.hide_screen_share()
            self.audio_manager.clear_peers()
            if self.main_stack.currentIndex() == 2:
                self.main_stack.setCurrentIndex(1)

    # ------------------ Audio & Indicators ------------------

    def _on_mic_toggled(self, is_muted: bool):
        self.audio_manager.is_muted = is_muted
        self.audio_manager.play_mute_chime(is_muted)
        self.tcp_client.send_user_media_state(is_muted, self.user_panel.is_deafened)

    def _on_deafen_toggled(self, is_deafened: bool):
        self.audio_manager.is_deafened = is_deafened
        self.audio_manager.play_deafen_chime(is_deafened)
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

    def _save_local_profile(self):
        try:
            import json
            cfg_path = Path.home() / ".vimcord_profile.json"
            data = {}
            if cfg_path.exists():
                try:
                    with open(cfg_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                except Exception:
                    data = {}
            key = self.my_user_id or self.my_username
            data[key] = {
                "username": self.my_username,
                "display_name": getattr(self, "my_display_name", self.my_username),
                "bio": getattr(self, "my_bio", ""),
                "status_text": self.my_status_text,
                "avatar_color": self.my_avatar_color,
                "avatar_image": getattr(self, "my_avatar_image", ""),
                "banner_color": getattr(self, "my_banner_color", "#5865F2"),
                "banner_image": getattr(self, "my_banner_image", "")
            }
            with open(cfg_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _load_local_profile(self):
        try:
            import json
            cfg_path = Path.home() / ".vimcord_profile.json"
            if not cfg_path.exists():
                return
            with open(cfg_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            key = self.my_user_id or self.my_username
            if key in data:
                cached = data[key]
                if not getattr(self, "my_display_name", "") and cached.get("display_name"):
                    self.my_display_name = cached["display_name"]
                if not getattr(self, "my_bio", "") and cached.get("bio"):
                    self.my_bio = cached["bio"]
                if not getattr(self, "my_avatar_image", "") and cached.get("avatar_image"):
                    self.my_avatar_image = cached["avatar_image"]
                if not getattr(self, "my_banner_color", "") and cached.get("banner_color"):
                    self.my_banner_color = cached["banner_color"]
                if not getattr(self, "my_banner_image", "") and cached.get("banner_image"):
                    self.my_banner_image = cached["banner_image"]
                if cached.get("status_text") and not self.my_status_text:
                    self.my_status_text = cached["status_text"]
        except Exception:
            pass

    def _on_settings_clicked(self):
        user_data = {
            "user_id": self.my_user_id,
            "username": self.my_username,
            "display_name": getattr(self, "my_display_name", self.my_username),
            "avatar_color": self.my_avatar_color,
            "avatar_image": getattr(self, "my_avatar_image", ""),
            "banner_color": getattr(self, "my_banner_color", "#5865F2"),
            "banner_image": getattr(self, "my_banner_image", ""),
            "bio": getattr(self, "my_bio", ""),
            "status_text": self.my_status_text
        }
        dlg = SettingsDialog(self.audio_manager, user_data, self)

        def _handle_profile_update(u, dname, s, c, img, bn_color, bn_img, b):
            self.my_username = u
            self.my_display_name = dname or u
            self.my_status_text = s
            self.my_avatar_color = c
            self.my_avatar_image = img
            self.my_banner_color = bn_color
            self.my_banner_image = bn_img
            self.my_bio = b
            self.user_panel.set_user(u, self.my_user_id, c, s, img, display_name=self.my_display_name)
            self.setWindowTitle(f"VimCord — {self.my_display_name} (@{u})")
            self.tcp_client.send_update_profile(u, dname, s, c, img, bn_color, bn_img, b)
            self._save_local_profile()

        dlg.profile_updated.connect(_handle_profile_update)
        dlg.password_changed.connect(lambda op, np: self.tcp_client.send_change_password(op, np))
        dlg.screen_settings_changed.connect(lambda res, fps, q: self.screen_capturer.set_stream_settings(res, fps, q))
        dlg.ptt_settings_changed.connect(self._on_ptt_settings_changed)
        dlg.theme_changed.connect(self._on_theme_changed)
        dlg.language_changed.connect(self._on_language_changed)
        dlg.dnd_toggled.connect(self._on_dnd_toggled)
        dlg.logout_requested.connect(self._on_logout_requested)
        dlg.exec()

    def _on_dnd_toggled(self, is_dnd: bool):
        self.dnd_mode = is_dnd

    def _on_language_changed(self, lang: str):
        self.current_language = lang
        set_language(lang)
        self._retranslate_ui()

    def _retranslate_ui(self):
        if hasattr(self, "connection_overlay"):
            self.connection_overlay.title_lbl.setText(t("connection_lost"))
            self.connection_overlay.desc_lbl.setText(t("disconnected_from_server"))
            self.connection_overlay.reconnect_btn.setText(f"🔄 {t('reconnect_now')}")

    def _apply_saved_theme(self):
        try:
            import json
            from pathlib import Path
            from vimcord.client.ui.styles import get_theme_qss
            cfg_path = Path.home() / ".vimcord_client.json"
            if cfg_path.exists():
                with open(cfg_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    theme = cfg.get("theme", "dark")
                    app = QApplication.instance()
                    if app:
                        app.setStyleSheet(get_theme_qss(theme))
                    else:
                        self.setStyleSheet(get_theme_qss(theme))
        except Exception:
            pass

    def _on_theme_changed(self, theme_name: str):
        from vimcord.client.ui.styles import get_theme_qss
        app = QApplication.instance()
        if app:
            app.setStyleSheet(get_theme_qss(theme_name))
        else:
            self.setStyleSheet(get_theme_qss(theme_name))

    def _on_ptt_settings_changed(self, is_ptt: bool, hotkey: str):
        self.audio_manager.set_ptt_mode(is_ptt)
        self.ptt_key = hotkey or "Space"

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
            full_info["display_name"] = getattr(self, "my_display_name", self.my_username)
            full_info["avatar_color"] = self.my_avatar_color
            full_info["avatar_image"] = getattr(self, "my_avatar_image", "")
            full_info["banner_color"] = getattr(self, "my_banner_color", "#5865F2")
            full_info["banner_image"] = getattr(self, "my_banner_image", "")
            full_info["bio"] = getattr(self, "my_bio", "")
            full_info["status_text"] = self.my_status_text
        else:
            if "display_name" not in full_info or not full_info["display_name"]:
                full_info["display_name"] = full_info.get("username", "User")

        dlg = UserProfileModal(full_info, is_self=is_self, is_friend=is_friend, parent=self)
        dlg.open_dm_clicked.connect(self._on_dm_user_selected)
        dlg.start_call_clicked.connect(self._on_call_user_requested)
        dlg.add_friend_clicked.connect(lambda uname: self.tcp_client.send_friend_request(uname))
        dlg.exec()

    def _open_my_profile(self):
        self._open_user_profile({
            "user_id": self.my_user_id,
            "username": self.my_username,
            "display_name": getattr(self, "my_display_name", self.my_username),
            "avatar_color": self.my_avatar_color,
            "avatar_image": getattr(self, "my_avatar_image", ""),
            "banner_color": getattr(self, "my_banner_color", "#5865F2"),
            "banner_image": getattr(self, "my_banner_image", ""),
            "bio": getattr(self, "my_bio", ""),
            "status_text": self.my_status_text
        })

    def _on_logout_requested(self):
        try:
            from vimcord.client.config import load_config, save_config
            cfg = load_config()
            cfg["auto_login"] = False
            cfg["saved_password"] = ""
            save_config(cfg)
        except Exception:
            pass
        self.close()

    def _on_peer_speaking(self, user_id: str, is_speaking: bool):
        self.voice_view.set_user_speaking(user_id, is_speaking)
        if user_id == self.my_user_id:
            self.user_panel.set_speaking(is_speaking)

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
                self.notify_user(
                    title="Friend Request",
                    message=f"{f.get('username')} sent you a friend request!",
                    icon_str="👥",
                    payload={"type": "friend_req", "peer_id": f.get("peer_id")}
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
            self.my_bio = user_dict.get("bio", getattr(self, "my_bio", ""))
            self.my_status_text = user_dict.get("status_text", self.my_status_text)
            self.user_panel.set_user(self.my_username, self.my_user_id, self.my_avatar_color, self.my_status_text, self.my_avatar_image)
            self.setWindowTitle(f"VimCord — {self.my_username}")
        else:
            QMessageBox.warning(self, "Profile Update", message or "Failed to update profile.")

    def _on_change_password_resp(self, success: bool, message: str):
        if success:
            QMessageBox.information(self, "Password", message)
        else:
            QMessageBox.warning(self, "Password", message)

    def _on_user_presence(self, user_dict: Dict[str, Any]):
        uid = user_dict.get("user_id")
        if not uid:
            return
        is_online = user_dict.get("online", True)
        if uid not in self.users:
            self.users[uid] = user_dict
        else:
            self.users[uid].update(user_dict)
        self.users[uid]["online"] = is_online

        self.channel_list.update_users(list(self.users.values()))
        self.friends_view.set_online_users(self.users)
        self.member_list.update_presence(uid, is_online, user_dict.get("status_text"))
        if self.current_room_id:
            self.tcp_client.send_get_room_members(self.current_room_id)

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
        if getattr(self, "_is_closing", False):
            return
        self.voice_bar.hide()
        self.voice_view.hide_screen_share()
        self.call_banner.stop()
        self.audio_manager.stop()
        self.udp_voice.stop()
        if hasattr(self, "connection_overlay"):
            self.connection_overlay.show_overlay()

    def _on_reconnect_requested(self):
        cfg = load_config()
        host = cfg.get("host", self.server_host)
        port = cfg.get("tcp_port", self.server_tcp_port)
        if not self.tcp_client.connect_to_server(host, port):
            if hasattr(self, "connection_overlay"):
                self.connection_overlay.set_reconnect_failed()
            return

        uname = cfg.get("username", self.my_username)
        pwd = cfg.get("saved_password", "")
        if uname and pwd:
            self.tcp_client.send_login(uname, pwd)
        else:
            if hasattr(self, "connection_overlay"):
                self.connection_overlay.set_reconnect_failed()

    def _on_reconnect_login_resp(self, ok: bool, data: dict):
        if ok:
            if hasattr(self, "connection_overlay"):
                self.connection_overlay.hide_overlay()
            rooms = data.get("rooms", [])
            users = data.get("users", [])
            friends = data.get("friends", [])
            self.rooms = {r["room_id"]: r for r in rooms}
            self.users = {u["user_id"]: u for u in users}
            self.friends = friends
            self.server_nav.set_rooms(list(self.rooms.values()))
            self.channel_list.set_friends(friends)
            self.friends_view.set_friends(friends)
            self.friends_view.set_online_users(self.users)
            self.audio_manager.start()
            self.udp_voice.start(self.my_user_id, self.server_host, self.server_udp_port)
            self.ping_timer.start()
        else:
            if hasattr(self, "connection_overlay") and self.connection_overlay.isVisible():
                self.connection_overlay.set_reconnect_failed()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "connection_overlay") and self.connection_overlay.isVisible():
            self.connection_overlay.resize(self.size())

    def _on_leave_room(self, room_id: str):
        ret = QMessageBox.question(
            self, "Leave Server",
            "Are you sure you want to leave this server?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if ret == QMessageBox.StandardButton.Yes:
            self.tcp_client.send_leave_room(room_id)

    def _on_leave_room_resp(self, success: bool, message: str, room_id: str):
        if success:
            self.rooms.pop(room_id, None)
            self.server_nav.remove_room_button(room_id)
            if self.current_room_id == room_id:
                self._on_dm_nav_selected()
            QMessageBox.information(self, "Server", "You left the server.")
        else:
            QMessageBox.warning(self, "Error", message or "Failed to leave server.")

    def _on_room_members_resp(self, room_id: str, members: List[Dict[str, Any]]):
        if self.current_room_id == room_id:
            self.member_list.set_members(room_id, members)

    def _send_ping(self):
        self.last_ping_time = time.time()
        self.tcp_client.send_ping()

    def _on_pong(self, client_ts: float):
        now = time.time()
        if client_ts > 0:
            ping_ms = max(1, int((now - client_ts) * 1000))
        elif self.last_ping_time > 0:
            ping_ms = max(1, int((now - self.last_ping_time) * 1000))
        else:
            ping_ms = 15
        self.current_ping = ping_ms
        self.voice_bar.update_ping(ping_ms)
        self.voice_view.update_connection_info(ping_ms, self.server_host, self.server_udp_port)

    def _matches_ptt_key(self, event) -> bool:
        k = event.key()
        if self.ptt_key == "Space" and k == Qt.Key.Key_Space:
            return True
        if self.ptt_key in ("Ctrl", "Control") and k in (Qt.Key.Key_Control,):
            return True
        if self.ptt_key == "Shift" and k in (Qt.Key.Key_Shift,):
            return True
        if self.ptt_key == "Alt" and k in (Qt.Key.Key_Alt,):
            return True
        if self.ptt_key in ("Caps", "Caps Lock") and k == Qt.Key.Key_CapsLock:
            return True
        if self.ptt_key in ("Return", "Enter") and k in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            return True
        if self.ptt_key == "Tab" and k == Qt.Key.Key_Tab:
            return True
        text = event.text().upper()
        if text and text == self.ptt_key.upper():
            return True
        from PyQt6.QtGui import QKeySequence
        seq = QKeySequence(k).toString()
        if seq and seq.upper() == self.ptt_key.upper():
            return True
        return False

    def keyPressEvent(self, event):
        if self.audio_manager.ptt_mode and not event.isAutoRepeat():
            if self._matches_ptt_key(event):
                self.audio_manager.set_ptt_active(True)
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if self.audio_manager.ptt_mode and not event.isAutoRepeat():
            if self._matches_ptt_key(event):
                self.audio_manager.set_ptt_active(False)
        super().keyReleaseEvent(event)

    def closeEvent(self, event):
        self._is_closing = True
        try:
            self.tcp_client.signals.disconnected.disconnect(self._on_server_disconnected)
        except Exception:
            pass
        self.ping_timer.stop()
        if self.tray_icon:
            self.tray_icon.hide()
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
