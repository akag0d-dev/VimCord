"""
Friends management view: Online, All, Pending requests, and Add Friend.
"""

from typing import List, Dict, Any, Optional
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QScrollArea, QFrame, QMessageBox
)


class FriendItemWidget(QWidget):
    call_clicked = pyqtSignal(str)   # user_id
    chat_clicked = pyqtSignal(str, str)   # user_id, username
    accept_clicked = pyqtSignal(str) # user_id
    decline_clicked = pyqtSignal(str) # user_id

    def __init__(self, friend_data: Dict[str, Any], is_online: bool = True, parent=None):
        super().__init__(parent)
        self.data = friend_data
        self.peer_id = friend_data.get("peer_id", "")
        self.username = friend_data.get("username", "User")
        self.avatar_color = friend_data.get("avatar_color", "#5865F2")
        self.status_text = friend_data.get("status_text", "В сети")
        self.is_incoming = friend_data.get("is_incoming", False)
        self.is_outgoing = friend_data.get("is_outgoing", False)
        self.is_online = is_online

        self.setFixedHeight(62)
        self._init_ui()

    def _init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(12)

        # Avatar circle
        initials = self.username[:2].upper() if self.username else "U"
        avatar = QLabel(initials)
        avatar.setFixedSize(40, 40)
        avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        avatar.setStyleSheet(f"""
            background-color: {self.avatar_color};
            color: #ffffff;
            font-weight: bold;
            font-size: 14px;
            border-radius: 20px;
        """)
        layout.addWidget(avatar)

        # Name and Status
        info_layout = QVBoxLayout()
        info_layout.setContentsMargins(0, 4, 0, 4)
        info_layout.setSpacing(2)

        name_lbl = QLabel(self.username)
        name_lbl.setStyleSheet("color: #ffffff; font-weight: bold; font-size: 14px;")
        info_layout.addWidget(name_lbl)

        status_str = "В сети" if self.is_online else "Не в сети"
        if self.status_text and self.status_text != "В сети":
            status_str += f" — {self.status_text}"
        status_lbl = QLabel(status_str)
        status_color = "#23a55a" if self.is_online else "#80848e"
        status_lbl.setStyleSheet(f"color: {status_color}; font-size: 12px;")
        info_layout.addWidget(status_lbl)

        layout.addLayout(info_layout, 1)

        # Action Buttons
        if self.is_incoming:
            acc_btn = QPushButton("Принять ✔️")
            acc_btn.setStyleSheet("""
                background-color: #23a55a; color: white; font-weight: bold;
                border-radius: 4px; padding: 6px 12px; border: none;
            """)
            acc_btn.clicked.connect(lambda: self.accept_clicked.emit(self.peer_id))
            layout.addWidget(acc_btn)

            dec_btn = QPushButton("Отклонить ✖️")
            dec_btn.setStyleSheet("""
                background-color: #4e5058; color: white;
                border-radius: 4px; padding: 6px 12px; border: none;
            """)
            dec_btn.clicked.connect(lambda: self.decline_clicked.emit(self.peer_id))
            layout.addWidget(dec_btn)

        elif self.is_outgoing:
            pending_lbl = QLabel("Заявка отправлена...")
            pending_lbl.setStyleSheet("color: #949ba4; font-size: 12px; font-style: italic;")
            layout.addWidget(pending_lbl)

            cancel_btn = QPushButton("Отменить")
            cancel_btn.setStyleSheet("""
                background-color: #4e5058; color: white;
                border-radius: 4px; padding: 6px 10px; border: none;
            """)
            cancel_btn.clicked.connect(lambda: self.decline_clicked.emit(self.peer_id))
            layout.addWidget(cancel_btn)

        else:
            # Accepted friend
            chat_btn = QPushButton("💬")
            chat_btn.setToolTip("Написать сообщение")
            chat_btn.setFixedSize(36, 36)
            chat_btn.setStyleSheet("""
                QPushButton {
                    background-color: #2b2d31;
                    border-radius: 18px;
                    font-size: 16px;
                    border: none;
                }
                QPushButton:hover {
                    background-color: #35373c;
                }
            """)
            chat_btn.clicked.connect(lambda: self.chat_clicked.emit(self.peer_id, self.username))
            layout.addWidget(chat_btn)

            call_btn = QPushButton("📞")
            call_btn.setToolTip("Позвонить лично")
            call_btn.setFixedSize(36, 36)
            call_btn.setStyleSheet("""
                QPushButton {
                    background-color: #2b2d31;
                    border-radius: 18px;
                    font-size: 16px;
                    border: none;
                }
                QPushButton:hover {
                    background-color: #23a55a;
                    color: white;
                }
            """)
            call_btn.clicked.connect(lambda: self.call_clicked.emit(self.peer_id))
            layout.addWidget(call_btn)


class FriendsView(QWidget):
    open_dm_chat = pyqtSignal(str, str)        # user_id, username
    start_call = pyqtSignal(str)              # user_id
    send_friend_req = pyqtSignal(str)         # target_username
    accept_friend_req = pyqtSignal(str)       # sender_uid
    decline_friend_req = pyqtSignal(str)      # peer_uid

    def __init__(self, parent=None):
        super().__init__(parent)
        self.friends: List[Dict[str, Any]] = []
        self.online_users: Dict[str, Dict[str, Any]] = {}
        self.current_tab = "online"  # "online", "all", "pending", "add"

        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 1. Top Navigation Tabs
        top_bar = QWidget()
        top_bar.setFixedHeight(48)
        top_bar.setStyleSheet("background-color: #313338; border-bottom: 1px solid #1f2023;")
        tb_layout = QHBoxLayout(top_bar)
        tb_layout.setContentsMargins(16, 0, 16, 0)
        tb_layout.setSpacing(12)

        icon_lbl = QLabel("👥")
        icon_lbl.setStyleSheet("font-size: 18px;")
        tb_layout.addWidget(icon_lbl)

        title = QLabel("Друзья")
        title.setStyleSheet("color: #ffffff; font-weight: bold; font-size: 15px;")
        tb_layout.addWidget(title)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFixedHeight(24)
        sep.setStyleSheet("background-color: #3f4147;")
        tb_layout.addWidget(sep)

        # Tab buttons
        self.btn_online = QPushButton("В сети")
        self.btn_all = QPushButton("Все")
        self.btn_pending = QPushButton("Ожидание")
        self.btn_add = QPushButton("Добавить в друзья")

        for b, tab in [
            (self.btn_online, "online"),
            (self.btn_all, "all"),
            (self.btn_pending, "pending"),
            (self.btn_add, "add")
        ]:
            b.setCheckable(True)
            b.setStyleSheet("""
                QPushButton {
                    background: transparent;
                    color: #b5bac1;
                    font-weight: 500;
                    padding: 6px 10px;
                    border-radius: 4px;
                    border: none;
                }
                QPushButton:hover {
                    background-color: #35373c;
                    color: #dbdee1;
                }
                QPushButton:checked {
                    background-color: #404249;
                    color: #ffffff;
                    font-weight: bold;
                }
            """)
            b.clicked.connect(lambda checked, t=tab: self._switch_tab(t))
            tb_layout.addWidget(b)

        # Style Add button green
        self.btn_add.setStyleSheet("""
            QPushButton {
                background-color: #23a55a;
                color: #ffffff;
                font-weight: bold;
                padding: 6px 12px;
                border-radius: 4px;
                border: none;
            }
            QPushButton:hover {
                background-color: #1f9250;
            }
        """)

        tb_layout.addStretch(1)
        main_layout.addWidget(top_bar)

        # 2. Main Content Area
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("background-color: #313338; border: none;")
        
        self.content_container = QWidget()
        self.content_container.setStyleSheet("background-color: #313338;")
        self.content_layout = QVBoxLayout(self.content_container)
        self.content_layout.setContentsMargins(20, 16, 20, 16)
        self.content_layout.setSpacing(6)
        self.content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.scroll.setWidget(self.content_container)
        main_layout.addWidget(self.scroll, 1)

        self._switch_tab("online")

    def set_friends(self, friends: List[Dict[str, Any]]):
        self.friends = friends
        # Update pending tab text with count
        pending_count = sum(1 for f in friends if f.get("is_incoming"))
        self.btn_pending.setText(f"Ожидание ({pending_count})" if pending_count > 0 else "Ожидание")
        self._render_current_tab()

    def set_online_users(self, online_users: Dict[str, Dict[str, Any]]):
        self.online_users = online_users
        self._render_current_tab()

    def _switch_tab(self, tab: str):
        self.current_tab = tab
        self.btn_online.setChecked(tab == "online")
        self.btn_all.setChecked(tab == "all")
        self.btn_pending.setChecked(tab == "pending")
        self.btn_add.setChecked(tab == "add")
        self._render_current_tab()

    def _clear_content(self):
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _render_current_tab(self):
        self._clear_content()

        if self.current_tab == "add":
            self._render_add_friend_view()
            return

        accepted_friends = [f for f in self.friends if f.get("friendship_status") == "accepted"]

        if self.current_tab == "online":
            online_friends = [f for f in accepted_friends if f.get("peer_id") in self.online_users and self.online_users[f.get("peer_id")].get("online", True)]
            lbl = QLabel(f"В СЕТИ — {len(online_friends)}")
            lbl.setStyleSheet("color: #949ba4; font-size: 12px; font-weight: bold; margin-bottom: 8px;")
            self.content_layout.addWidget(lbl)

            if not online_friends:
                self._render_empty_label("Никого из друзей нет в сети.")
                return

            for f in online_friends:
                self._add_friend_item(f, is_online=True)

        elif self.current_tab == "all":
            lbl = QLabel(f"ВСЕ ДРУЗЬЯ — {len(accepted_friends)}")
            lbl.setStyleSheet("color: #949ba4; font-size: 12px; font-weight: bold; margin-bottom: 8px;")
            self.content_layout.addWidget(lbl)

            if not accepted_friends:
                self._render_empty_label("У вас пока нет добавленных друзей.")
                return

            for f in accepted_friends:
                is_on = f.get("peer_id") in self.online_users and self.online_users[f.get("peer_id")].get("online", True)
                self._add_friend_item(f, is_online=is_on)

        elif self.current_tab == "pending":
            pending_list = [f for f in self.friends if f.get("friendship_status") == "pending"]
            lbl = QLabel(f"ЗАПРОСЫ В ДРУЗЬЯ — {len(pending_list)}")
            lbl.setStyleSheet("color: #949ba4; font-size: 12px; font-weight: bold; margin-bottom: 8px;")
            self.content_layout.addWidget(lbl)

            if not pending_list:
                self._render_empty_label("Нет ожидающих запросов в друзья.")
                return

            for f in pending_list:
                self._add_friend_item(f, is_online=False)

    def _add_friend_item(self, f_data: Dict[str, Any], is_online: bool):
        item = FriendItemWidget(f_data, is_online=is_online)
        item.chat_clicked.connect(self.open_dm_chat.emit)
        item.call_clicked.connect(self.start_call.emit)
        item.accept_clicked.connect(self.accept_friend_req.emit)
        item.decline_clicked.connect(self.decline_friend_req.emit)
        self.content_layout.addWidget(item)

    def _render_empty_label(self, text: str):
        lbl = QLabel(text)
        lbl.setStyleSheet("color: #80848e; font-size: 13px; padding: 20px 0;")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.content_layout.addWidget(lbl)

    def _render_add_friend_view(self):
        title = QLabel("ДОБАВИТЬ В ДРУЗЬЯ")
        title.setStyleSheet("color: #ffffff; font-weight: bold; font-size: 16px;")
        self.content_layout.addWidget(title)

        desc = QLabel("Вы можете отправить запрос в друзья любому пользователю VimCord, зная его имя.")
        desc.setStyleSheet("color: #949ba4; font-size: 13px; margin-bottom: 12px;")
        self.content_layout.addWidget(desc)

        input_box = QWidget()
        input_box.setStyleSheet("background-color: #1e1f22; border-radius: 8px; padding: 6px 12px;")
        ib_layout = QHBoxLayout(input_box)
        ib_layout.setContentsMargins(6, 4, 6, 4)

        self.add_input = QLineEdit()
        self.add_input.setPlaceholderText("Введите имя пользователя...")
        self.add_input.setStyleSheet("background: transparent; border: none; color: #ffffff; font-size: 15px;")
        self.add_input.returnPressed.connect(self._on_send_request)
        ib_layout.addWidget(self.add_input, 1)

        send_req_btn = QPushButton("Отправить запрос")
        send_req_btn.setStyleSheet("""
            background-color: #5865F2;
            color: #ffffff;
            font-weight: bold;
            padding: 8px 16px;
            border-radius: 4px;
            border: none;
        """)
        send_req_btn.clicked.connect(self._on_send_request)
        ib_layout.addWidget(send_req_btn)

        self.content_layout.addWidget(input_box)

        self.feedback_lbl = QLabel("")
        self.feedback_lbl.setStyleSheet("font-size: 13px; margin-top: 8px;")
        self.content_layout.addWidget(self.feedback_lbl)

    def _on_send_request(self):
        target = self.add_input.text().strip()
        if not target:
            return
        self.send_friend_req.emit(target)
        self.add_input.clear()

    def set_feedback(self, success: bool, message: str):
        if hasattr(self, "feedback_lbl") and self.feedback_lbl:
            color = "#23a55a" if success else "#f23f43"
            self.feedback_lbl.setStyleSheet(f"color: {color}; font-size: 13px; margin-top: 8px;")
            self.feedback_lbl.setText(message)
