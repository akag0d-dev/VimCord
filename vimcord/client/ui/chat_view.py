"""
Persistent text chat view with history caching, word wrapping, and Discord message styling.
"""

import datetime
from typing import Dict, Any, List, Optional
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTextBrowser
)


class ChatView(QWidget):
    send_message_requested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_target_id = "ch-general"
        self.target_name = "общий-чат"
        self.is_channel = True

        # In-memory history cache: target_id -> list of message dicts
        self.message_cache: Dict[str, List[Dict[str, Any]]] = {}

        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 1. Header Bar
        self.header_bar = QWidget()
        self.header_bar.setObjectName("chat_header")
        self.header_bar.setFixedHeight(48)
        self.header_bar.setStyleSheet("background-color: #313338; border-bottom: 1px solid #1f2023;")
        h_layout = QHBoxLayout(self.header_bar)
        h_layout.setContentsMargins(16, 0, 16, 0)

        self.title_icon = QLabel("#")
        self.title_icon.setStyleSheet("color: #80848e; font-size: 20px; font-weight: bold; margin-right: 6px;")
        h_layout.addWidget(self.title_icon)

        self.title_label = QLabel("общий-чат")
        self.title_label.setStyleSheet("color: #ffffff; font-size: 15px; font-weight: bold;")
        h_layout.addWidget(self.title_label, 1)

        main_layout.addWidget(self.header_bar)

        # 2. Messages Browser (stretches to take all available height)
        self.browser = QTextBrowser()
        self.browser.setObjectName("chat_history")
        self.browser.setOpenExternalLinks(True)
        self.browser.setStyleSheet("""
            QTextBrowser {
                background-color: #313338;
                border: none;
                color: #dbdee1;
                font-size: 14px;
                padding: 14px 18px;
            }
        """)
        main_layout.addWidget(self.browser, 1)

        # 3. Input bar (fixed height at the bottom)
        input_container = QWidget()
        input_container.setFixedHeight(64)
        input_container.setStyleSheet("background-color: #313338; padding: 6px 16px 12px 16px;")
        in_layout = QHBoxLayout(input_container)
        in_layout.setContentsMargins(16, 4, 16, 10)
        in_layout.setSpacing(10)

        self.msg_input = QLineEdit()
        self.msg_input.setObjectName("chat_input")
        self.msg_input.setPlaceholderText(f"Написать в #{self.target_name}")
        self.msg_input.setStyleSheet("""
            QLineEdit {
                background-color: #383a40;
                color: #ffffff;
                border-radius: 8px;
                padding: 10px 14px;
                font-size: 14px;
                border: none;
            }
        """)
        self.msg_input.returnPressed.connect(self._on_send)
        in_layout.addWidget(self.msg_input, 1)

        self.send_btn = QPushButton("Отправить")
        self.send_btn.setObjectName("send_btn")
        self.send_btn.setStyleSheet("""
            QPushButton {
                background-color: #5865F2;
                color: #ffffff;
                font-weight: bold;
                border-radius: 6px;
                padding: 10px 18px;
                border: none;
            }
            QPushButton:hover {
                background-color: #4752c4;
            }
        """)
        self.send_btn.clicked.connect(self._on_send)
        in_layout.addWidget(self.send_btn)

        main_layout.addWidget(input_container)

    def set_target(self, target_id: str, title: str, is_channel: bool = True):
        self.current_target_id = target_id
        self.target_name = title
        self.is_channel = is_channel

        prefix = "#" if is_channel else "@"
        self.title_icon.setText(prefix)
        self.title_label.setText(title)
        self.msg_input.setPlaceholderText(f"Написать в {prefix}{title}")

        # Render cached messages for this target
        self._render_history()

    def set_history(self, target_id: str, messages: List[Dict[str, Any]]):
        """Updates the local cache and re-renders if current active target."""
        self.message_cache[target_id] = messages
        if target_id == self.current_target_id:
            self._render_history()

    def append_message(self, msg: Dict[str, Any]):
        t_id = msg.get("target_id")
        if t_id not in self.message_cache:
            self.message_cache[t_id] = []
        
        # Check if already in cache by msg_id
        msg_id = msg.get("msg_id")
        if not any(m.get("msg_id") == msg_id for m in self.message_cache[t_id]):
            self.message_cache[t_id].append(msg)

        if t_id == self.current_target_id:
            self._append_message_html(msg)
            self._scroll_to_bottom()

    def _render_history(self):
        self.browser.clear()
        prefix = "#" if self.is_channel else "@"
        type_str = "канал" if self.is_channel else "личный диалог"

        welcome_html = f"""
        <div style='margin-bottom: 24px; color: #949ba4;'>
            <h2 style='color: #ffffff; margin-bottom: 6px; font-size: 20px;'>Добро пожаловать в {prefix}{self.target_name}!</h2>
            <div style='font-size: 13px;'>Это начало истории для {type_str} <b>{self.target_name}</b>.</div>
        </div>
        <hr style='border: 0; border-top: 1px solid #35373c; margin-bottom: 16px;'/>
        """
        self.browser.append(welcome_html)

        messages = self.message_cache.get(self.current_target_id, [])
        for m in messages:
            self._append_message_html(m)

        self._scroll_to_bottom()

    def _append_message_html(self, msg: Dict[str, Any]):
        sender = msg.get("sender_name", "User")
        content = msg.get("content", "")
        ts = msg.get("timestamp", 0)

        time_str = datetime.datetime.fromtimestamp(ts).strftime("%H:%M") if ts else ""
        content_escaped = (
            content.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("\n", "<br/>")
        )

        initials = sender[:2].upper() if sender else "U"

        html = f"""
        <div style='margin-bottom: 14px; word-wrap: break-word; overflow-wrap: break-word;'>
            <table style='width: 100%; border-collapse: collapse;'>
                <tr>
                    <td style='vertical-align: top; width: 44px;'>
                        <div style='width: 36px; height: 36px; background-color: #5865F2; color: #ffffff;
                                    font-weight: bold; font-size: 14px; line-height: 36px; text-align: center;
                                    border-radius: 18px;'>
                            {initials}
                        </div>
                    </td>
                    <td style='vertical-align: top; padding-left: 8px;'>
                        <span style='color: #5865F2; font-weight: bold; font-size: 14px;'>{sender}</span>
                        <span style='color: #949ba4; font-size: 11px; margin-left: 8px;'>{time_str}</span>
                        <div style='color: #dbdee1; margin-top: 4px; font-size: 14px; line-height: 1.4;'>{content_escaped}</div>
                    </td>
                </tr>
            </table>
        </div>
        """
        self.browser.append(html)

    def _scroll_to_bottom(self):
        sb = self.browser.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_send(self):
        text = self.msg_input.text().strip()
        if not text:
            return
        self.msg_input.clear()
        self.send_message_requested.emit(text)
