"""
Text chat view with messages history and input field.
"""

import datetime
from typing import Dict, Any
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTextBrowser
)


class ChatView(QWidget):
    send_message_requested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.target_name = "общий-чат"
        self.is_channel = True

        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 1. Chat Header
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

        # 2. Messages Browser
        self.browser = QTextBrowser()
        self.browser.setObjectName("chat_history")
        self.browser.setOpenExternalLinks(True)
        self.browser.setStyleSheet("""
            QTextBrowser {
                background-color: #313338;
                border: none;
                color: #dbdee1;
                font-size: 14px;
                padding: 12px 16px;
            }
        """)
        main_layout.addWidget(self.browser, 1)

        # 3. Input bar
        input_container = QWidget()
        input_container.setFixedHeight(68)
        input_container.setStyleSheet("background-color: #313338; padding: 10px 16px;")
        in_layout = QHBoxLayout(input_container)
        in_layout.setContentsMargins(16, 8, 16, 12)
        in_layout.setSpacing(10)

        self.msg_input = QLineEdit()
        self.msg_input.setObjectName("chat_input")
        self.msg_input.setPlaceholderText(f"Написать в #{self.target_name}")
        self.msg_input.returnPressed.connect(self._on_send)
        in_layout.addWidget(self.msg_input, 1)

        self.send_btn = QPushButton("Отправить")
        self.send_btn.setObjectName("send_btn")
        self.send_btn.clicked.connect(self._on_send)
        in_layout.addWidget(self.send_btn)

        main_layout.addWidget(input_container)

    def set_target(self, name: str, is_channel: bool = True):
        self.target_name = name
        self.is_channel = is_channel
        
        prefix = "#" if is_channel else "@"
        self.title_icon.setText(prefix)
        self.title_label.setText(name)
        self.msg_input.setPlaceholderText(f"Написать в {prefix}{name}")
        self.browser.clear()
        
        # Welcoming header inside chat
        type_str = "канал" if is_channel else "личный диалог"
        welcome_html = f"""
        <div style='margin-bottom: 20px; color: #949ba4;'>
            <h2 style='color: #ffffff; margin-bottom: 4px;'>Добро пожаловать в {prefix}{name}!</h2>
            <div>Это начало истории для {type_str} <b>{name}</b>.</div>
        </div>
        <hr style='border: 0; border-top: 1px solid #35373c; margin-bottom: 12px;'/>
        """
        self.browser.append(welcome_html)

    def append_message(self, msg: Dict[str, Any]):
        sender = msg.get("sender_name", "User")
        content = msg.get("content", "")
        ts = msg.get("timestamp", 0)
        
        time_str = datetime.datetime.fromtimestamp(ts).strftime("%H:%M") if ts else ""
        
        # Escape HTML entities
        content_escaped = content.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        html = f"""
        <div style='margin-bottom: 10px;'>
            <span style='color: #5865F2; font-weight: bold;'>{sender}</span>
            <span style='color: #949ba4; font-size: 11px; margin-left: 6px;'>{time_str}</span>
            <div style='color: #dbdee1; margin-top: 3px; font-size: 14px;'>{content_escaped}</div>
        </div>
        """
        self.browser.append(html)
        # Auto scroll down
        sb = self.browser.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_send(self):
        text = self.msg_input.text().strip()
        if not text:
            return
        self.msg_input.clear()
        self.send_message_requested.emit(text)
