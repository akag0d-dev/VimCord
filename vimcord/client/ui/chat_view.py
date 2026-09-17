"""
Persistent text chat view with history caching, word wrapping, Discord message styling,
round avatars, photo attachments, voice messages, message deletion, and member list toggle.
"""

import base64
import datetime
import os
from typing import Dict, Any, List, Optional
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QByteArray, QBuffer, QIODevice, QUrl
from PyQt6.QtGui import QDesktopServices, QPixmap, QIcon, QTextDocument, QImage
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTextBrowser, QFileDialog, QFrame
)
from vimcord.client.ui.avatar_helper import get_round_avatar_pixmap


class ChatView(QWidget):
    # content, image_b64, voice_b64, voice_duration
    send_message_requested = pyqtSignal(str, str, str, float)
    # msg_id, target_type, target_id
    delete_message_requested = pyqtSignal(str, str, str)
    # voice_b64
    play_voice_requested = pyqtSignal(str)
    # toggle right member list
    toggle_members_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_target_id = "ch-general"
        self.target_name = "общий-чат"
        self.is_channel = True
        self.current_user_id = ""
        self.audio_manager = None

        # Attached image state
        self.attached_image_b64: str = ""
        self.attached_filename: str = ""

        # Voice recording state
        self.is_recording_voice: bool = False
        self.voice_record_seconds: int = 0
        self.voice_timer = QTimer(self)
        self.voice_timer.setInterval(1000)
        self.voice_timer.timeout.connect(self._on_voice_timer_tick)

        # In-memory history cache: target_id -> list of message dicts
        self.message_cache: Dict[str, List[Dict[str, Any]]] = {}

        self._init_ui()

    def set_current_user_id(self, user_id: str):
        self.current_user_id = user_id

    def set_audio_manager(self, audio_manager):
        self.audio_manager = audio_manager

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

        # Member list toggle button
        self.members_btn = QPushButton("👥")
        self.members_btn.setToolTip("Показать/скрыть список участников")
        self.members_btn.setFixedSize(34, 34)
        self.members_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #b5bac1;
                font-size: 16px;
                border-radius: 4px;
                border: none;
            }
            QPushButton:hover {
                background-color: #35373c;
                color: #ffffff;
            }
        """)
        self.members_btn.clicked.connect(self.toggle_members_requested.emit)
        h_layout.addWidget(self.members_btn)

        main_layout.addWidget(self.header_bar)

        # 2. Messages Browser
        self.browser = QTextBrowser()
        self.browser.setObjectName("chat_history")
        self.browser.setOpenLinks(False)
        self.browser.setOpenExternalLinks(False)
        self.browser.anchorClicked.connect(self._on_anchor_clicked)
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

        # 3. Attachment Preview strip (hidden by default)
        self.preview_strip = QWidget()
        self.preview_strip.setFixedHeight(46)
        self.preview_strip.setStyleSheet("background-color: #2b2d31; border-top: 1px solid #1f2023; padding: 4px 16px;")
        p_layout = QHBoxLayout(self.preview_strip)
        p_layout.setContentsMargins(16, 4, 16, 4)
        p_layout.setSpacing(10)

        self.preview_img_label = QLabel()
        self.preview_img_label.setFixedSize(38, 38)
        self.preview_img_label.setStyleSheet("border-radius: 4px; background-color: #1e1f22;")
        p_layout.addWidget(self.preview_img_label)

        self.preview_text_label = QLabel("Прикреплено фото")
        self.preview_text_label.setStyleSheet("color: #dbdee1; font-size: 13px;")
        p_layout.addWidget(self.preview_text_label, 1)

        self.clear_attach_btn = QPushButton("✕")
        self.clear_attach_btn.setFixedSize(26, 26)
        self.clear_attach_btn.setStyleSheet("""
            QPushButton {
                background-color: #35373c;
                color: #ffffff;
                font-weight: bold;
                border-radius: 13px;
                border: none;
            }
            QPushButton:hover {
                background-color: #ed4245;
            }
        """)
        self.clear_attach_btn.clicked.connect(self._clear_attachment)
        p_layout.addWidget(self.clear_attach_btn)

        self.preview_strip.setVisible(False)
        main_layout.addWidget(self.preview_strip)

        # 4. Input bar (fixed height at the bottom)
        input_container = QWidget()
        input_container.setFixedHeight(64)
        input_container.setStyleSheet("background-color: #313338; padding: 6px 16px 12px 16px;")
        in_layout = QHBoxLayout(input_container)
        in_layout.setContentsMargins(16, 4, 16, 10)
        in_layout.setSpacing(8)

        # 📎 Attachment button
        self.attach_btn = QPushButton("📎")
        self.attach_btn.setToolTip("Прикрепить фотографию")
        self.attach_btn.setFixedSize(38, 38)
        self.attach_btn.setStyleSheet("""
            QPushButton {
                background-color: #383a40;
                color: #b5bac1;
                font-size: 16px;
                border-radius: 8px;
                border: none;
            }
            QPushButton:hover {
                background-color: #404249;
                color: #ffffff;
            }
        """)
        self.attach_btn.clicked.connect(self._on_choose_attachment)
        in_layout.addWidget(self.attach_btn)

        # Text input
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

        # 🎙️ Voice message button
        self.voice_btn = QPushButton("🎙️")
        self.voice_btn.setToolTip("Голосовое сообщение (нажмите для записи)")
        self.voice_btn.setFixedSize(38, 38)
        self.voice_btn.setStyleSheet("""
            QPushButton {
                background-color: #383a40;
                color: #b5bac1;
                font-size: 16px;
                border-radius: 8px;
                border: none;
            }
            QPushButton:hover {
                background-color: #404249;
                color: #ffffff;
            }
        """)
        self.voice_btn.clicked.connect(self._toggle_voice_recording)
        self.voice_btn.hide()  # Hidden per user request, code preserved
        in_layout.addWidget(self.voice_btn)

        # Send button
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
        self.members_btn.setVisible(is_channel)

        # Render cached messages for this target
        self._render_history()

    def set_history(self, target_id: str, messages: List[Dict[str, Any]]):
        """Updates local cache and re-renders if active target."""
        self.message_cache[target_id] = messages
        if target_id == self.current_target_id:
            self._render_history()

    def append_message(self, msg: Dict[str, Any]):
        t_id = msg.get("target_id")
        if t_id not in self.message_cache:
            self.message_cache[t_id] = []
        
        msg_id = msg.get("msg_id", "")
        # Check if already cached by ID
        if any(m.get("msg_id") == msg_id for m in self.message_cache[t_id]):
            return

        # Check for optimistic local message match (same sender and content within 5s)
        matched_local = None
        for m in self.message_cache[t_id]:
            if m.get("msg_id", "").startswith("loc-") and m.get("sender_id") == msg.get("sender_id"):
                if m.get("content") == msg.get("content") and m.get("image_data") == msg.get("image_data"):
                    matched_local = m
                    break
        
        if matched_local:
            # Update local placeholder with real server msg_id
            matched_local["msg_id"] = msg_id
            return

        self.message_cache[t_id].append(msg)

        if t_id == self.current_target_id:
            self._append_message_html(msg)
            self._scroll_to_bottom()

    def remove_message(self, msg_id: str, target_id: str):
        if target_id in self.message_cache:
            self.message_cache[target_id] = [m for m in self.message_cache[target_id] if m.get("msg_id") != msg_id]
        if target_id == self.current_target_id:
            self._render_history()

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
        msg_id = msg.get("msg_id", "")
        sender_id = msg.get("sender_id", "")
        sender = msg.get("sender_name", "User")
        content = msg.get("content", "")
        ts = msg.get("timestamp", 0)
        avatar_color = msg.get("avatar_color", "#5865F2")
        avatar_image = msg.get("avatar_image", "")
        image_data = msg.get("image_data", "")
        voice_data = msg.get("voice_data", "")
        voice_duration = float(msg.get("voice_duration", 0.0))

        time_str = datetime.datetime.fromtimestamp(ts).strftime("%H:%M") if ts else ""
        content_escaped = (
            content.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("\n", "<br/>")
        )

        # 1. Round Avatar registered as Qt Document Image Resource
        av_pixmap = get_round_avatar_pixmap(36, sender, avatar_color, avatar_image)
        av_key = f"av_{abs(hash(sender + avatar_color + avatar_image[:20]))}"
        av_url = QUrl(f"res://avatar/{av_key}.png")
        self.browser.document().addResource(QTextDocument.ResourceType.ImageResource, av_url, av_pixmap.toImage())
        avatar_html = f"<img src='res://avatar/{av_key}.png' width='36' height='36' />"

        # 2. Delete button for own messages
        delete_html = ""
        if sender_id and self.current_user_id and sender_id == self.current_user_id and msg_id:
            delete_html = f"""
            <a href='delete:{msg_id}' style='color: #ed4245; text-decoration: none; font-size: 12px; margin-left: 10px;' title='Удалить сообщение'>🗑️</a>
            """

        # 3. Attachment Image registered as Qt Document Image Resource
        image_html = ""
        if image_data:
            try:
                clean_b64 = image_data
                if "," in clean_b64:
                    clean_b64 = clean_b64.split(",", 1)[1]
                raw_bytes = base64.b64decode(clean_b64)
                qimg = QImage()
                if qimg.loadFromData(raw_bytes):
                    max_w, max_h = 380, 260
                    if qimg.width() > max_w or qimg.height() > max_h:
                        qimg = qimg.scaled(max_w, max_h, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                    img_key = f"img_{msg_id or abs(hash(image_data[:30]))}"
                    img_url = QUrl(f"res://img/{img_key}.jpg")
                    self.browser.document().addResource(QTextDocument.ResourceType.ImageResource, img_url, qimg)
                    image_html = f"""
                    <div style='margin-top: 6px;'>
                        <a href='view_image:{msg_id}' style='text-decoration: none;' title='Нажмите, чтобы открыть'>
                            <img src='res://img/{img_key}.jpg' width='{qimg.width()}' height='{qimg.height()}' style='border-radius: 6px;' />
                        </a>
                    </div>
                    """
            except Exception:
                pass

        # 4. Voice message card
        voice_html = ""
        if voice_data:
            dur_text = f"{voice_duration:.1f}с" if voice_duration > 0 else "голосовое"
            voice_html = f"""
            <div style='margin-top: 6px; padding: 4px 0;'>
                <a href='play_voice:{msg_id}' style='color: #5865F2; text-decoration: none; font-weight: bold; font-size: 13px;'>
                    ▶️ Прослушать ({dur_text})
                </a>
            </div>
            """

        html = f"""
        <div style='margin-bottom: 14px; word-wrap: break-word; overflow-wrap: break-word;'>
            <table style='width: 100%; border-collapse: collapse;'>
                <tr>
                    <td style='vertical-align: top; width: 44px;'>
                        {avatar_html}
                    </td>
                    <td style='vertical-align: top; padding-left: 8px;'>
                        <span style='color: #5865F2; font-weight: bold; font-size: 14px;'>{sender}</span>
                        <span style='color: #949ba4; font-size: 11px; margin-left: 8px;'>{time_str}</span>
                        {delete_html}
                        {f"<div style='color: #dbdee1; margin-top: 4px; font-size: 14px; line-height: 1.4;'>{content_escaped}</div>" if content else ""}
                        {image_html}
                        {voice_html}
                    </td>
                </tr>
            </table>
        </div>
        """
        self.browser.append(html)

    def _scroll_to_bottom(self):
        sb = self.browser.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_anchor_clicked(self, url: QUrl):
        url_str = url.toString()
        if url_str.startswith("delete:"):
            msg_id = url_str.removeprefix("delete:")
            target_type = "channel" if self.is_channel else "dm"
            self.delete_message_requested.emit(msg_id, target_type, self.current_target_id)
        elif url_str.startswith("view_image:"):
            msg_id = url_str.removeprefix("view_image:")
            messages = self.message_cache.get(self.current_target_id, [])
            msg = next((m for m in messages if m.get("msg_id") == msg_id), None)
            if msg and msg.get("image_data"):
                try:
                    from vimcord.client.ui.image_viewer import ImageViewerModal
                    dlg = ImageViewerModal(msg["image_data"], self)
                    dlg.exec()
                except Exception as e:
                    logger.error(f"Error opening image modal: {e}")
        elif url_str.startswith("play_voice:"):
            msg_id = url_str.removeprefix("play_voice:")
            messages = self.message_cache.get(self.current_target_id, [])
            msg = next((m for m in messages if m.get("msg_id") == msg_id), None)
            if msg and msg.get("voice_data"):
                if self.audio_manager:
                    self.audio_manager.play_voice_msg(msg["voice_data"], float(msg.get("voice_duration", 0.0)))
                else:
                    self.play_voice_requested.emit(msg["voice_data"])
        elif url.scheme() in ("http", "https"):
            QDesktopServices.openUrl(url)

    def _on_choose_attachment(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Выберите изображение", "",
            "Изображения (*.png *.jpg *.jpeg *.webp)"
        )
        if not path or not os.path.exists(path):
            return

        pm = QPixmap(path)
        if pm.isNull():
            return

        # Scale down if very large (max 1280x720)
        if pm.width() > 1280 or pm.height() > 720:
            pm = pm.scaled(1280, 720, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)

        byte_arr = QByteArray()
        buf = QBuffer(byte_arr)
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        pm.save(buf, "JPEG", 75)

        self.attached_image_b64 = base64.b64encode(byte_arr.data()).decode("ascii")
        self.attached_filename = os.path.basename(path)

        # Show preview
        preview_thumb = pm.scaled(38, 38, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
        self.preview_img_label.setPixmap(preview_thumb)
        self.preview_text_label.setText(f"Прикреплено: {self.attached_filename}")
        self.preview_strip.setVisible(True)

    def _clear_attachment(self):
        self.attached_image_b64 = ""
        self.attached_filename = ""
        self.preview_strip.setVisible(False)

    def _toggle_voice_recording(self):
        if not self.audio_manager:
            return

        if not self.is_recording_voice:
            # Start recording
            self.is_recording_voice = True
            self.voice_record_seconds = 0
            self.audio_manager.start_recording_voice_msg()
            self.voice_btn.setText("⏹️ 0:00")
            self.voice_btn.setStyleSheet("""
                QPushButton {
                    background-color: #ED4245;
                    color: #ffffff;
                    font-weight: bold;
                    font-size: 13px;
                    border-radius: 8px;
                    border: none;
                }
            """)
            self.voice_btn.setFixedWidth(75)
            self.voice_timer.start()
        else:
            # Stop recording and send
            self.voice_timer.stop()
            self.is_recording_voice = False
            b64_voice, duration = self.audio_manager.stop_recording_voice_msg()
            
            self.voice_btn.setText("🎙️")
            self.voice_btn.setFixedSize(38, 38)
            self.voice_btn.setStyleSheet("""
                QPushButton {
                    background-color: #383a40;
                    color: #b5bac1;
                    font-size: 16px;
                    border-radius: 8px;
                    border: none;
                }
                QPushButton:hover {
                    background-color: #404249;
                    color: #ffffff;
                }
            """)

            if b64_voice and duration > 0.3:
                self.send_message_requested.emit("", "", b64_voice, duration)

    def _on_voice_timer_tick(self):
        self.voice_record_seconds += 1
        m = self.voice_record_seconds // 60
        s = self.voice_record_seconds % 60
        self.voice_btn.setText(f"⏹️ {m}:{s:02d}")

    def _on_send(self):
        text = self.msg_input.text().strip()
        img = self.attached_image_b64

        if not text and not img:
            return

        self.msg_input.clear()
        self._clear_attachment()
        self.send_message_requested.emit(text, img, "", 0.0)
