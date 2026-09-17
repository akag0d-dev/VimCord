"""
Sidebar widget displaying channels (in room mode) or friends and DM chats (in DM mode).
"""

from typing import Dict, Any, List, Optional
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QMessageBox
)
from vimcord.client.ui.avatar_helper import get_round_avatar_pixmap


class ChannelListWidget(QWidget):
    text_channel_selected = pyqtSignal(str, str, str)   # room_id, channel_id, name
    voice_channel_selected = pyqtSignal(str, str, str)  # room_id, channel_id, name
    create_channel_requested = pyqtSignal(str)          # room_id
    delete_room_requested = pyqtSignal(str)             # room_id
    leave_room_requested = pyqtSignal(str)              # room_id
    invite_room_requested = pyqtSignal(str)             # room_id
    dm_user_selected = pyqtSignal(str, str)             # user_id, username
    call_user_requested = pyqtSignal(str)               # user_id
    friends_tab_selected = pyqtSignal()                 # Open friends view
    user_profile_requested = pyqtSignal(dict)           # user_dict

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("sidebar_widget")
        self.setFixedWidth(240)

        self.current_mode = "@me"  # "@me" or room_id
        self.current_room_data: Optional[Dict[str, Any]] = None
        self.current_users_list: List[Dict[str, Any]] = []
        self.friends_list: List[Dict[str, Any]] = []
        self.my_user_id: str = ""
        
        self.active_text_ch_id: Optional[str] = None
        self.active_voice_ch_id: Optional[str] = None
        self.active_dm_user_id: Optional[str] = None

        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 1. Header Bar
        self.header_widget = QWidget()
        self.header_widget.setFixedHeight(48)
        self.header_widget.setStyleSheet("background-color: #2b2d31; border-bottom: 1px solid #1f2023;")
        header_layout = QHBoxLayout(self.header_widget)
        header_layout.setContentsMargins(16, 0, 8, 0)
        header_layout.setSpacing(4)

        self.header_title = QLabel("Direct Messages")
        self.header_title.setStyleSheet("font-weight: bold; font-size: 15px; color: #ffffff;")
        header_layout.addWidget(self.header_title, 1)

        # Invite button (Room mode only)
        self.invite_btn = QPushButton("🔗")
        self.invite_btn.setToolTip("Create Server Invite")
        self.invite_btn.setFixedSize(26, 26)
        self.invite_btn.setStyleSheet("""
            QPushButton {
                background: transparent; font-size: 14px; border: none; border-radius: 4px;
            }
            QPushButton:hover { background-color: #35373c; }
        """)
        self.invite_btn.clicked.connect(self._on_invite_click)
        header_layout.addWidget(self.invite_btn)

        # Add Channel button (Room mode only)
        self.add_ch_btn = QPushButton("+")
        self.add_ch_btn.setToolTip("Create Channel")
        self.add_ch_btn.setFixedSize(26, 26)
        self.add_ch_btn.setStyleSheet("""
            QPushButton {
                background: transparent; color: #949ba4; font-size: 18px; font-weight: bold;
                border: none; border-radius: 4px;
            }
            QPushButton:hover { background-color: #35373c; color: #dbdee1; }
        """)
        self.add_ch_btn.clicked.connect(self._on_add_channel)
        header_layout.addWidget(self.add_ch_btn)

        # Leave Room button
        self.leave_room_btn = QPushButton("🚪")
        self.leave_room_btn.setToolTip("Leave Server")
        self.leave_room_btn.setFixedSize(26, 26)
        self.leave_room_btn.setStyleSheet("""
            QPushButton {
                background: transparent; font-size: 13px; border: none; border-radius: 4px;
            }
            QPushButton:hover { background-color: #35373c; }
        """)
        self.leave_room_btn.clicked.connect(self._on_leave_room)
        header_layout.addWidget(self.leave_room_btn)

        # Delete Room button (Owner only)
        self.del_room_btn = QPushButton("🗑️")
        self.del_room_btn.setToolTip("Delete Server")
        self.del_room_btn.setFixedSize(26, 26)
        self.del_room_btn.setStyleSheet("""
            QPushButton {
                background: transparent; font-size: 13px; border: none; border-radius: 4px;
            }
            QPushButton:hover { background-color: #35373c; }
        """)
        self.del_room_btn.clicked.connect(self._on_delete_room)
        header_layout.addWidget(self.del_room_btn)

        main_layout.addWidget(self.header_widget)

        # 2. Scrollable Body
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet("background: transparent; border: none;")

        self.content_widget = QWidget()
        self.content_widget.setStyleSheet("background: transparent;")
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(8, 10, 8, 10)
        self.content_layout.setSpacing(4)
        self.content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.scroll.setWidget(self.content_widget)
        main_layout.addWidget(self.scroll, 1)

    def set_my_user_id(self, user_id: str):
        self.my_user_id = user_id

    def show_dm_mode(self, users: List[Dict[str, Any]]):
        self.current_mode = "@me"
        self.current_users_list = users
        self.header_title.setText("Direct Messages")
        self.invite_btn.hide()
        self.add_ch_btn.hide()
        self.leave_room_btn.hide()
        self.del_room_btn.hide()
        self._render_dm_list()

    def show_room_mode(self, room: Dict[str, Any]):
        self.current_mode = room.get("room_id")
        self.current_room_data = room
        self.header_title.setText(room.get("name", "Server"))
        self.invite_btn.show()
        self.add_ch_btn.show()

        is_custom_room = (room.get("room_id") != "room-default")
        is_owner = (room.get("owner_id") == self.my_user_id)

        self.leave_room_btn.setVisible(is_custom_room and not is_owner)
        self.del_room_btn.setVisible(is_custom_room and is_owner)
        self._render_room_channels()

    def _on_leave_room(self):
        if self.current_mode and self.current_mode != "@me":
            self.leave_room_requested.emit(self.current_mode)

    def set_friends(self, friends: List[Dict[str, Any]]):
        self.friends_list = friends
        if self.current_mode == "@me":
            self._render_dm_list()

    def update_users(self, users: List[Dict[str, Any]]):
        self.current_users_list = users
        if self.current_mode == "@me":
            self._render_dm_list()
        elif self.current_room_data:
            self._render_room_channels()

    def _clear_content(self):
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _render_dm_list(self):
        self._clear_content()

        # Friends Nav Button
        friends_btn = QPushButton("👥  Friends")
        friends_btn.setStyleSheet("""
            QPushButton {
                background-color: #35373c; color: #ffffff; font-weight: bold;
                border-radius: 6px; padding: 10px 14px; text-align: left; border: none; font-size: 14px;
            }
            QPushButton:hover { background-color: #404249; }
        """)
        friends_btn.clicked.connect(self.friends_tab_selected.emit)
        self.content_layout.addWidget(friends_btn)

        # Section Header
        sec_label = QLabel("DIRECT MESSAGES")
        sec_label.setStyleSheet("color: #949ba4; font-size: 11px; font-weight: bold; padding: 14px 8px 4px 8px;")
        self.content_layout.addWidget(sec_label)

        # Privacy filter: ONLY show confirmed friends in DMs
        confirmed_friends = [f for f in self.friends_list if f.get("friendship_status") == "accepted"]
        if not confirmed_friends:
            empty_lbl = QLabel("No friends yet\nGo to the 'Friends' tab to add friends 👥")
            empty_lbl.setWordWrap(True)
            empty_lbl.setStyleSheet("color: #80848e; font-size: 12px; padding: 10px 8px; line-height: 1.4;")
            self.content_layout.addWidget(empty_lbl)
            return

        for f in confirmed_friends:
            uid = f.get("peer_id")
            uname = f.get("username", "User")
            color = f.get("avatar_color", "#5865F2")
            avatar_img = f.get("avatar_image", "")

            # Match online status
            is_online = False
            in_call = False
            matched_user_dict = None
            for u in self.current_users_list:
                if u.get("user_id") == uid:
                    is_online = u.get("online", True)
                    in_call = u.get("in_call", False)
                    color = u.get("avatar_color", color)
                    avatar_img = u.get("avatar_image", avatar_img)
                    matched_user_dict = u
                    break

            if not matched_user_dict:
                matched_user_dict = {
                    "user_id": uid,
                    "username": uname,
                    "avatar_color": color,
                    "avatar_image": avatar_img,
                    "status_text": f.get("status_text", ""),
                    "online": is_online
                }

            item_w = QWidget()
            is_selected = (uid == self.active_dm_user_id)
            bg = "#404249" if is_selected else "transparent"
            item_w.setStyleSheet(f"""
                QWidget {{ background-color: {bg}; border-radius: 4px; }}
                QWidget:hover {{ background-color: #35373c; }}
            """)
            i_layout = QHBoxLayout(item_w)
            i_layout.setContentsMargins(6, 4, 6, 4)
            i_layout.setSpacing(8)

            # Circular avatar pixmap
            av_lbl = QLabel()
            av_lbl.setFixedSize(26, 26)
            av_lbl.setPixmap(get_round_avatar_pixmap(26, uname, color, avatar_img))
            av_lbl.setCursor(Qt.CursorShape.PointingHandCursor)
            av_lbl.setToolTip("View Profile")
            av_lbl.mousePressEvent = lambda e, ud=matched_user_dict: self.user_profile_requested.emit(ud)
            i_layout.addWidget(av_lbl)

            # Name button
            name_btn = QPushButton(uname)
            name_btn.setStyleSheet("text-align: left; color: #dbdee1; font-weight: 500; border: none; background: transparent; font-size: 13px;")
            name_btn.clicked.connect(lambda checked, i_uid=uid, i_name=uname: self._on_user_chat_clicked(i_uid, i_name))
            i_layout.addWidget(name_btn, 1)

            # Online dot
            dot_color = "#f23f43" if in_call else ("#23a55a" if is_online else "#80848e")
            dot = QLabel("●")
            dot.setStyleSheet(f"color: {dot_color}; font-size: 11px;")
            i_layout.addWidget(dot)

            # Quick Call button
            call_btn = QPushButton("📞")
            call_btn.setToolTip("Call")
            call_btn.setFixedSize(24, 24)
            call_btn.setStyleSheet("""
                QPushButton { background: transparent; border: none; border-radius: 12px; font-size: 11px; }
                QPushButton:hover { background-color: #23a55a; color: white; }
            """)
            call_btn.clicked.connect(lambda checked, i_uid=uid: self.call_user_requested.emit(i_uid))
            i_layout.addWidget(call_btn)

            self.content_layout.addWidget(item_w)

    def _render_room_channels(self):
        if not self.current_room_data:
            return
        self._clear_content()

        channels = self.current_room_data.get("channels", [])
        text_channels = [c for c in channels if c.get("channel_type") == "text"]
        voice_channels = [c for c in channels if c.get("channel_type") == "voice"]

        # Text channels section
        lbl_text = QLabel("TEXT CHANNELS")
        lbl_text.setStyleSheet("color: #949ba4; font-size: 11px; font-weight: bold; padding: 6px 8px;")
        self.content_layout.addWidget(lbl_text)

        for c in text_channels:
            cid = c.get("channel_id")
            cname = c.get("name")
            btn = QPushButton(f"#  {cname}")
            is_active = (cid == self.active_text_ch_id)
            bg = "#404249" if is_active else "transparent"
            color = "#ffffff" if is_active else "#949ba4"
            btn.setStyleSheet(f"""
                QPushButton {{
                    text-align: left; background-color: {bg}; color: {color};
                    border-radius: 4px; padding: 7px 10px; border: none; font-weight: 500; font-size: 13px;
                }}
                QPushButton:hover {{ background-color: #35373c; color: #dbdee1; }}
            """)
            btn.clicked.connect(lambda checked, r_id=self.current_mode, ch_id=cid, ch_nm=cname: self._on_text_ch_clicked(r_id, ch_id, ch_nm))
            self.content_layout.addWidget(btn)

        # Voice channels section
        lbl_voice = QLabel("VOICE CHANNELS")
        lbl_voice.setStyleSheet("color: #949ba4; font-size: 11px; font-weight: bold; padding: 12px 8px 6px 8px;")
        self.content_layout.addWidget(lbl_voice)

        for vc in voice_channels:
            cid = vc.get("channel_id")
            raw_cname = vc.get("name", "Voice")
            # Clean leading speaker icon if already present to prevent double 🔊 🔊
            clean_name = raw_cname.lstrip("🔊 ").strip()
            voice_users = vc.get("voice_users", [])
            is_connected = (cid == self.active_voice_ch_id)

            bg = "#35373c" if is_connected else "transparent"
            color = "#23a55a" if is_connected else "#949ba4"

            v_btn = QPushButton(f"🔊  {clean_name}")
            v_btn.setStyleSheet(f"""
                QPushButton {{
                    text-align: left; background-color: {bg}; color: {color};
                    border-radius: 4px; padding: 7px 10px; border: none; font-weight: 500; font-size: 13px;
                }}
                QPushButton:hover {{ background-color: #35373c; color: #dbdee1; }}
            """)
            v_btn.clicked.connect(lambda checked, r_id=self.current_mode, ch_id=cid, ch_nm=clean_name: self._on_voice_ch_clicked(r_id, ch_id, ch_nm))
            self.content_layout.addWidget(v_btn)

            if voice_users:
                u_container = QWidget()
                u_layout = QVBoxLayout(u_container)
                u_layout.setContentsMargins(20, 0, 8, 4)
                u_layout.setSpacing(2)

                for uid in voice_users:
                    uname = uid
                    u_dict = None
                    is_muted = False
                    is_deaf = False
                    for u in self.current_users_list:
                        if u.get("user_id") == uid:
                            uname = u.get("username", uid)
                            is_muted = u.get("is_muted", False)
                            is_deaf = u.get("is_deafened", False)
                            u_dict = u
                            break

                    media_badge = ""
                    if is_deaf:
                        media_badge = " 🎧"
                    elif is_muted:
                        media_badge = " 🔇"

                    vu_btn = QPushButton(f"🎙️ {uname}{media_badge}")
                    vu_btn.setToolTip("Click to view profile")
                    vu_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                    vu_btn.setStyleSheet("""
                        QPushButton {
                            text-align: left; background: transparent; color: #dbdee1;
                            font-size: 12px; border: none; padding: 3px 6px; border-radius: 3px;
                        }
                        QPushButton:hover { background-color: #35373c; color: #ffffff; }
                    """)
                    if not u_dict:
                        u_dict = {"user_id": uid, "username": uname}
                    vu_btn.clicked.connect(lambda checked, ud=u_dict: self.user_profile_requested.emit(ud))
                    u_layout.addWidget(vu_btn)

                self.content_layout.addWidget(u_container)

    def _on_text_ch_clicked(self, room_id: str, channel_id: str, name: str):
        self.active_text_ch_id = channel_id
        self._render_room_channels()
        self.text_channel_selected.emit(room_id, channel_id, name)

    def _on_voice_ch_clicked(self, room_id: str, channel_id: str, name: str):
        self.voice_channel_selected.emit(room_id, channel_id, name)

    def _on_user_chat_clicked(self, user_id: str, username: str):
        self.active_dm_user_id = user_id
        self._render_dm_list()
        self.dm_user_selected.emit(user_id, username)

    def set_active_voice(self, channel_id: Optional[str]):
        self.active_voice_ch_id = channel_id
        if self.current_mode != "@me":
            self._render_room_channels()

    def _on_invite_click(self):
        if self.current_mode and self.current_mode != "@me":
            self.invite_room_requested.emit(self.current_mode)

    def _on_add_channel(self):
        if self.current_mode and self.current_mode != "@me":
            self.create_channel_requested.emit(self.current_mode)

    def _on_delete_room(self):
        if self.current_mode and self.current_mode != "@me":
            ret = QMessageBox.question(
                self, "Delete Server",
                f"Are you sure you want to delete server '{self.header_title.text()}'?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if ret == QMessageBox.StandardButton.Yes:
                self.delete_room_requested.emit(self.current_mode)
