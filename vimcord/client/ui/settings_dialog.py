"""
Comprehensive Discord-style Settings and Account Management Dialog.
Overhauled with Discord Dark aesthetic, profile banner, bio editor,
Voice Activity (VAD) / Push-to-Talk (PTT), Noise Gate toggle, and Screen Share presets.
"""

from typing import Dict, Any, Optional
import re
import json
from pathlib import Path
import base64
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QPixmap, QKeySequence, QKeyEvent
from PyQt6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QSlider, QProgressBar, QStackedWidget,
    QListWidget, QListWidgetItem, QFrame, QMessageBox, QFileDialog,
    QRadioButton, QCheckBox, QScrollArea, QButtonGroup
)
from vimcord.client.config import load_config, save_config
from vimcord.client.audio.audio_manager import AudioManager
from vimcord.client.ui.avatar_helper import get_round_avatar_pixmap
from vimcord.client.i18n import t, set_language


class SettingsDialog(QDialog):
    profile_updated = pyqtSignal(str, str, str, str, str, str, str, str)  # username, display_name, status_text, avatar_color, avatar_image, banner_color, banner_image, bio
    password_changed = pyqtSignal(str, str)                                 # old_pass, new_pass
    logout_requested = pyqtSignal()
    screen_settings_changed = pyqtSignal(str, int, int)                     # resolution, fps, quality
    ptt_settings_changed = pyqtSignal(bool, str)                            # ptt_mode, ptt_key
    theme_changed = pyqtSignal(str)                                         # "dark", "amoled", "light"
    language_changed = pyqtSignal(str)                                      # "ru", "en"
    dnd_toggled = pyqtSignal(bool)

    DISCORD_COLORS = [
        ("#5865F2", "Blurple"),
        ("#57F287", "Green"),
        ("#FEE75C", "Yellow"),
        ("#EB459E", "Fuchsia"),
        ("#ED4245", "Red"),
        ("#9B59B6", "Purple"),
        ("#1ABC9C", "Teal")
    ]

    def __init__(self, audio_manager: AudioManager, user_data: Dict[str, Any], parent=None):
        super().__init__(parent)
        self.audio_manager = audio_manager
        self.user_data = user_data

        self.username = user_data.get("username", "User")
        self.display_name = user_data.get("display_name") or self.username
        self.user_id = user_data.get("user_id", "")
        self.status_text = user_data.get("status_text", "Online")
        self.avatar_color = user_data.get("avatar_color", "#5865F2")
        self.avatar_image = user_data.get("avatar_image", "")
        self.banner_color = user_data.get("banner_color", "#5865F2")
        self.banner_image = user_data.get("banner_image", "")
        self.bio = user_data.get("bio", "")
        self.selected_color = self.avatar_color
        self.selected_banner_color = self.banner_color

        cfg = load_config()
        self.current_theme = cfg.get("theme", "dark")
        self.current_language = cfg.get("language", "en")
        self.dnd_mode = cfg.get("dnd_mode", False)

        self.ptt_mode = getattr(self.audio_manager, "ptt_mode", False)
        self.ptt_key = cfg.get("ptt_key", "Space")
        self.noise_suppression = getattr(self.audio_manager, "noise_suppression", True)
        self._is_recording_key = False

        self.setWindowTitle("Settings — VimCord")
        self.resize(780, 560)
        self.setMinimumSize(720, 500)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        self._testing_mic = False
        self._current_mic_level = 0.0
        self._orig_callback = self.audio_manager.on_mic_frame

        self._init_ui()
        self._load_audio_devices()

        self.meter_timer = QTimer(self)
        self.meter_timer.setInterval(40)
        self.meter_timer.timeout.connect(self._update_meter)

    def _init_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 1. Left Categories Sidebar (210px)
        sidebar = QWidget()
        sidebar.setFixedWidth(210)
        sidebar.setStyleSheet("background-color: #2b2d31; border-right: 1px solid #1f2023;")
        sb_layout = QVBoxLayout(sidebar)
        sb_layout.setContentsMargins(16, 24, 12, 16)
        sb_layout.setSpacing(6)

        header_usr = QLabel("USER SETTINGS")
        header_usr.setStyleSheet("color: #949ba4; font-size: 11px; font-weight: bold; margin-bottom: 4px;")
        sb_layout.addWidget(header_usr)

        self.nav_list = QListWidget()
        self.nav_list.setStyleSheet("""
            QListWidget { background: transparent; border: none; outline: none; }
            QListWidget::item {
                color: #b5bac1; padding: 8px 12px; border-radius: 4px; font-weight: 500;
            }
            QListWidget::item:hover { background-color: #35373c; color: #dbdee1; }
            QListWidget::item:selected { background-color: #404249; color: #ffffff; font-weight: bold; }
        """)
        self.nav_list.addItem("👤 My Account")
        self.nav_list.addItem("🎙️ Voice & Video")
        self.nav_list.addItem("🎨 Appearance")
        self.nav_list.currentRowChanged.connect(self._on_category_changed)
        sb_layout.addWidget(self.nav_list)

        sb_layout.addStretch(1)

        # Logout button
        logout_btn = QPushButton("Log Out")
        logout_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent; color: #f23f43; font-weight: bold;
                border: 1px solid #f23f43; border-radius: 4px; padding: 8px; text-align: center;
            }
            QPushButton:hover { background-color: #f23f43; color: white; }
        """)
        logout_btn.clicked.connect(self._on_logout)
        sb_layout.addWidget(logout_btn)

        main_layout.addWidget(sidebar)

        # 2. Right Stacked Content Pages
        self.pages = QStackedWidget()
        self.pages.setStyleSheet("background-color: #313338;")

        self.page_account = self._create_account_page()
        self.page_voice = self._create_voice_page()
        self.page_appearance = self._create_appearance_page()

        self.pages.addWidget(self.page_account)
        self.pages.addWidget(self.page_voice)
        self.pages.addWidget(self.page_appearance)

        main_layout.addWidget(self.pages, 1)
        self.nav_list.setCurrentRow(0)

    # ------------------ Page 1: My Account ------------------

    def _create_account_page(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background-color: #313338; }")

        w = QWidget()
        w.setStyleSheet("background-color: #313338;")
        layout = QVBoxLayout(w)
        layout.setContentsMargins(30, 24, 30, 24)
        layout.setSpacing(14)

        title = QLabel("My Account")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #ffffff;")
        layout.addWidget(title)

        # Profile Card Banner Preview
        card = QWidget()
        card.setStyleSheet("background-color: #1e1f22; border-radius: 8px;")
        card_l = QVBoxLayout(card)
        card_l.setContentsMargins(0, 0, 0, 14)
        card_l.setSpacing(0)

        self.banner_preview = QLabel()
        self.banner_preview.setFixedHeight(85)
        self._refresh_banner_preview()
        card_l.addWidget(self.banner_preview)

        # Avatar and user info row overlapping banner
        top_av_box = QHBoxLayout()
        top_av_box.setContentsMargins(14, -30, 14, 0)
        top_av_box.setSpacing(14)

        self.avatar_preview = QLabel()
        self.avatar_preview.setFixedSize(60, 60)
        self.avatar_preview.setStyleSheet("border: 3px solid #1e1f22; border-radius: 30px; background-color: #1e1f22;")
        self.avatar_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._refresh_avatar_preview()
        top_av_box.addWidget(self.avatar_preview)

        info_l = QVBoxLayout()
        info_l.setContentsMargins(0, 30, 0, 0)
        info_l.setSpacing(2)
        self.card_dname_lbl = QLabel(self.display_name)
        self.card_dname_lbl.setStyleSheet("color: #ffffff; font-size: 16px; font-weight: bold;")
        info_l.addWidget(self.card_dname_lbl)

        self.card_uname_lbl = QLabel(f"@{self.username} • ID: {self.user_id}")
        self.card_uname_lbl.setStyleSheet("color: #949ba4; font-size: 11px;")
        info_l.addWidget(self.card_uname_lbl)

        self.card_status_lbl = QLabel(self.status_text or "Online")
        self.card_status_lbl.setStyleSheet("color: #23a55a; font-size: 12px;")
        info_l.addWidget(self.card_status_lbl)

        top_av_box.addLayout(info_l, 1)
        card_l.addLayout(top_av_box)

        layout.addWidget(card)

        # Banner Upload / Remove Row
        bn_btns_row = QHBoxLayout()
        bn_btns_row.setSpacing(10)

        upload_bn_btn = QPushButton("🖼️ Upload Banner Image")
        upload_bn_btn.setStyleSheet("""
            QPushButton {
                background-color: #4e5058; color: white; font-weight: bold;
                padding: 6px 12px; border-radius: 4px; border: none; font-size: 12px;
            }
            QPushButton:hover { background-color: #6d6f78; }
        """)
        upload_bn_btn.clicked.connect(self._on_upload_banner)
        bn_btns_row.addWidget(upload_bn_btn)

        remove_bn_btn = QPushButton("✕ Reset Banner Image")
        remove_bn_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent; color: #f23f43; border: 1px solid #f23f43;
                padding: 6px 12px; border-radius: 4px; font-size: 12px;
            }
            QPushButton:hover { background-color: #f23f43; color: white; }
        """)
        remove_bn_btn.clicked.connect(self._on_remove_banner)
        bn_btns_row.addWidget(remove_bn_btn)
        bn_btns_row.addStretch(1)
        layout.addLayout(bn_btns_row)

        # Avatar Upload / Remove Row
        av_btns_row = QHBoxLayout()
        av_btns_row.setSpacing(10)

        upload_av_btn = QPushButton("📁 Upload Avatar (PNG/JPG)")
        upload_av_btn.setStyleSheet("""
            QPushButton {
                background-color: #4e5058; color: white; font-weight: bold;
                padding: 6px 12px; border-radius: 4px; border: none; font-size: 12px;
            }
            QPushButton:hover { background-color: #6d6f78; }
        """)
        upload_av_btn.clicked.connect(self._on_upload_avatar)
        av_btns_row.addWidget(upload_av_btn)

        remove_av_btn = QPushButton("✕ Reset to Accent Color")
        remove_av_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent; color: #f23f43; border: 1px solid #f23f43;
                padding: 6px 12px; border-radius: 4px; font-size: 12px;
            }
            QPushButton:hover { background-color: #f23f43; color: white; }
        """)
        remove_av_btn.clicked.connect(self._on_remove_avatar)
        av_btns_row.addWidget(remove_av_btn)
        av_btns_row.addStretch(1)
        layout.addLayout(av_btns_row)

        # Profile Edits Form
        layout.addWidget(QLabel("DISPLAY NAME (Visible to other members):"))
        self.dname_edit = QLineEdit(self.display_name)
        self.dname_edit.setPlaceholderText("Enter your display name (e.g. Alex 🔥, Алексей)...")
        self.dname_edit.setStyleSheet("background-color: #1e1f22; color: #ffffff; padding: 8px; border-radius: 4px; border: none;")
        layout.addWidget(self.dname_edit)

        layout.addWidget(QLabel("USERNAME (@username, English letters, numbers, _, -):"))
        self.uname_edit = QLineEdit(self.username)
        self.uname_edit.setStyleSheet("background-color: #1e1f22; color: #ffffff; padding: 8px; border-radius: 4px; border: none;")
        layout.addWidget(self.uname_edit)

        layout.addWidget(QLabel("CUSTOM STATUS:"))
        self.status_edit = QLineEdit(self.status_text)
        self.status_edit.setPlaceholderText("e.g. Coding Python, Playing...")
        self.status_edit.setStyleSheet("background-color: #1e1f22; color: #ffffff; padding: 8px; border-radius: 4px; border: none;")
        layout.addWidget(self.status_edit)

        layout.addWidget(QLabel("ABOUT ME (BIO):"))
        self.bio_edit = QLineEdit(self.bio)
        self.bio_edit.setPlaceholderText("Tell the world about yourself...")
        self.bio_edit.setStyleSheet("background-color: #1e1f22; color: #ffffff; padding: 8px; border-radius: 4px; border: none;")
        layout.addWidget(self.bio_edit)

        # Avatar color palette
        layout.addWidget(QLabel("AVATAR ACCENT COLOR:"))
        color_row = QHBoxLayout()
        color_row.setSpacing(8)
        self.color_buttons = []
        for hex_code, name in self.DISCORD_COLORS:
            btn = QPushButton()
            btn.setFixedSize(28, 28)
            btn.setToolTip(name)
            is_cur = (hex_code.lower() == self.avatar_color.lower())
            border = "2px solid #ffffff" if is_cur else "none"
            btn.setStyleSheet(f"background-color: {hex_code}; border-radius: 14px; border: {border};")
            btn.clicked.connect(lambda checked, h=hex_code: self._select_avatar_color(h))
            color_row.addWidget(btn)
            self.color_buttons.append((btn, hex_code))
        color_row.addStretch(1)
        layout.addLayout(color_row)

        save_prof_btn = QPushButton("Save Changes")
        save_prof_btn.setStyleSheet("""
            background-color: #5865F2; color: white; font-weight: bold;
            padding: 8px 16px; border-radius: 4px; border: none; max-width: 240px;
        """)
        save_prof_btn.clicked.connect(self._on_save_profile)
        layout.addWidget(save_prof_btn)

        # Password Change Divider
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background-color: #35373c; margin: 10px 0;")
        layout.addWidget(sep)

        pw_title = QLabel("CHANGE PASSWORD:")
        pw_title.setStyleSheet("color: #b5bac1; font-weight: bold; font-size: 11px;")
        layout.addWidget(pw_title)

        pw_row = QHBoxLayout()
        self.old_pw_edit = QLineEdit()
        self.old_pw_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.old_pw_edit.setPlaceholderText("Current password")
        self.old_pw_edit.setStyleSheet("background-color: #1e1f22; color: #ffffff; padding: 8px; border-radius: 4px; border: none;")
        pw_row.addWidget(self.old_pw_edit)

        self.new_pw_edit = QLineEdit()
        self.new_pw_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.new_pw_edit.setPlaceholderText("New password (min 4 chars)")
        self.new_pw_edit.setStyleSheet("background-color: #1e1f22; color: #ffffff; padding: 8px; border-radius: 4px; border: none;")
        pw_row.addWidget(self.new_pw_edit)

        change_pw_btn = QPushButton("Update Password")
        change_pw_btn.setStyleSheet("""
            background-color: #4e5058; color: white; font-weight: bold;
            padding: 8px 14px; border-radius: 4px; border: none;
        """)
        change_pw_btn.clicked.connect(self._on_change_password)
        pw_row.addWidget(change_pw_btn)
        layout.addLayout(pw_row)

        layout.addStretch(1)
        scroll.setWidget(w)
        return scroll

    def _refresh_banner_preview(self):
        if self.banner_image:
            try:
                clean_b64 = self.banner_image
                if "," in clean_b64:
                    clean_b64 = clean_b64.split(",", 1)[1]
                raw_bytes = base64.b64decode(clean_b64)
                pm = QPixmap()
                if pm.loadFromData(raw_bytes):
                    scaled = pm.scaled(520, 85, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
                    self.banner_preview.setPixmap(scaled)
                    self.banner_preview.setScaledContents(True)
                    return
            except Exception:
                pass
        self.banner_preview.clear()
        self.banner_preview.setStyleSheet(f"background-color: {self.selected_banner_color}; border-top-left-radius: 8px; border-top-right-radius: 8px;")

    def _on_upload_banner(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Banner Image", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.webp)"
        )
        if not file_path:
            return
        try:
            with open(file_path, "rb") as f:
                raw = f.read()
            if len(raw) > 2 * 1024 * 1024:
                QMessageBox.warning(self, "File Too Large", "Please select a banner image under 2 MB.")
                return
            b64 = base64.b64encode(raw).decode("utf-8")
            self.banner_image = b64
            self._refresh_banner_preview()
            QMessageBox.information(self, "Banner Selected", "Banner image loaded! Click 'Save Changes' to apply.")
        except Exception as e:
            QMessageBox.critical(self, "Upload Error", f"Failed to read file: {e}")

    def _on_remove_banner(self):
        self.banner_image = ""
        self._refresh_banner_preview()

    def _refresh_avatar_preview(self):
        pixmap = get_round_avatar_pixmap(
            54, self.display_name or self.username, self.selected_color, self.avatar_image
        )
        self.avatar_preview.setPixmap(pixmap)

    def _on_upload_avatar(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Profile Image", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.webp)"
        )
        if not file_path:
            return
        try:
            with open(file_path, "rb") as f:
                raw = f.read()
            if len(raw) > 1024 * 1024:
                QMessageBox.warning(self, "File Too Large", "Please select an image under 1 MB.")
                return
            b64 = base64.b64encode(raw).decode("utf-8")
            self.avatar_image = b64
            self._refresh_avatar_preview()
            QMessageBox.information(self, "Avatar Selected", "Avatar loaded! Click 'Save Changes' to apply.")
        except Exception as e:
            QMessageBox.critical(self, "Upload Error", f"Failed to read file: {e}")

    def _on_remove_avatar(self):
        self.avatar_image = ""
        self._refresh_avatar_preview()

    def _select_avatar_color(self, hex_code: str):
        self.selected_color = hex_code
        self.selected_banner_color = hex_code
        self._refresh_avatar_preview()
        self._refresh_banner_preview()
        for btn, h in self.color_buttons:
            border = "2px solid #ffffff" if h == hex_code else "none"
            btn.setStyleSheet(f"background-color: {hex_code}; border-radius: 14px; border: {border};")

    def _on_save_profile(self):
        new_dname = self.dname_edit.text().strip() or self.username
        new_name = self.uname_edit.text().strip()
        new_status = self.status_edit.text().strip()
        new_bio = self.bio_edit.text().strip()

        username_regex = re.compile(r"^[a-zA-Z0-9_-]{2,32}$")
        if not new_name or not username_regex.match(new_name):
            QMessageBox.warning(
                self, "Validation Error",
                "Username must be 2-32 characters long and consist only of English letters, numbers, hyphens, and underscores."
            )
            return

        # Check if username already exists in MainWindow.users
        parent = self.parent()
        if parent and hasattr(parent, "users") and isinstance(parent.users, dict):
            for uid, udata in parent.users.items():
                if uid != self.user_id:
                    existing_name = (udata.get("username") or "").strip().lower()
                    if existing_name and existing_name == new_name.lower():
                        QMessageBox.warning(self, "Error", f"The username '{new_name}' is already taken. Please choose a different username.")
                        return

        self.username = new_name
        self.display_name = new_dname
        self.status_text = new_status
        self.bio = new_bio
        self.avatar_color = self.selected_color
        self.banner_color = self.selected_banner_color

        self.card_dname_lbl.setText(self.display_name)
        self.card_uname_lbl.setText(f"@{self.username} • ID: {self.user_id}")
        self.card_status_lbl.setText(new_status or "Online")

        self.profile_updated.emit(
            self.username, self.display_name, self.status_text,
            self.selected_color, self.avatar_image,
            self.selected_banner_color, self.banner_image, self.bio
        )
        QMessageBox.information(self, "Success", "Profile updated successfully!")

    def _on_change_password(self):
        old_p = self.old_pw_edit.text().strip()
        new_p = self.new_pw_edit.text().strip()
        if not old_p or not new_p:
            QMessageBox.warning(self, "Error", "Please fill in both password fields!")
            return
        if len(new_p) < 4:
            QMessageBox.warning(self, "Error", "New password must be at least 4 characters long!")
            return

        self.password_changed.emit(old_p, new_p)
        self.old_pw_edit.clear()
        self.new_pw_edit.clear()

    def _on_logout(self):
        ret = QMessageBox.question(
            self, "Log Out", "Are you sure you want to log out of your account?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if ret == QMessageBox.StandardButton.Yes:
            self.logout_requested.emit()
            self.accept()

    # ------------------ Page 2: Voice & Video ------------------

    def _create_voice_page(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background-color: #313338; }")

        w = QWidget()
        w.setStyleSheet("background-color: #313338;")
        layout = QVBoxLayout(w)
        layout.setContentsMargins(30, 24, 30, 24)
        layout.setSpacing(12)

        title = QLabel("Voice & Video Settings")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #ffffff;")
        layout.addWidget(title)

        # 1. Devices
        layout.addWidget(QLabel("INPUT DEVICE (MICROPHONE):"))
        self.in_combo = QComboBox()
        self.in_combo.currentIndexChanged.connect(lambda idx: self.audio_manager.set_input_device(self.in_combo.currentData()))
        layout.addWidget(self.in_combo)

        layout.addWidget(QLabel("OUTPUT DEVICE (SPEAKERS):"))
        self.out_combo = QComboBox()
        self.out_combo.currentIndexChanged.connect(lambda idx: self.audio_manager.set_output_device(self.out_combo.currentData()))
        layout.addWidget(self.out_combo)

        # 2. Volumes
        self.mic_lbl = QLabel(f"Input Volume: {int(self.audio_manager.mic_volume * 100)}%")
        layout.addWidget(self.mic_lbl)
        self.mic_slider = QSlider(Qt.Orientation.Horizontal)
        self.mic_slider.setRange(0, 200)
        self.mic_slider.setValue(int(self.audio_manager.mic_volume * 100))
        self.mic_slider.valueChanged.connect(self._on_mic_vol)
        layout.addWidget(self.mic_slider)

        self.out_lbl = QLabel(f"Output Volume: {int(self.audio_manager.output_volume * 100)}%")
        layout.addWidget(self.out_lbl)
        self.out_slider = QSlider(Qt.Orientation.Horizontal)
        self.out_slider.setRange(0, 200)
        self.out_slider.setValue(int(self.audio_manager.output_volume * 100))
        self.out_slider.valueChanged.connect(self._on_out_vol)
        layout.addWidget(self.out_slider)

        # 3. Input Mode: VAD vs PTT
        layout.addWidget(QLabel("INPUT MODE:"))
        mode_box = QHBoxLayout()
        mode_box.setSpacing(12)

        vad_card = QWidget()
        vad_card.setStyleSheet("""
            QWidget {
                background-color: #2b2d31; border: 1px solid #383a40; border-radius: 6px; padding: 6px;
            }
        """)
        vad_layout = QVBoxLayout(vad_card)
        vad_layout.setContentsMargins(10, 8, 10, 8)
        self.vad_radio = QRadioButton("Voice Activity (VAD)")
        self.vad_radio.setStyleSheet("""
            QRadioButton {
                color: #ffffff; font-weight: bold; font-size: 13px;
            }
            QRadioButton::indicator {
                width: 16px; height: 16px; border-radius: 8px; border: 2px solid #80848e; background: #1e1f22;
            }
            QRadioButton::indicator:checked {
                background-color: #23a55a; border-color: #23a55a;
            }
        """)
        vad_hint = QLabel("Automatically transmits audio when speaking.")
        vad_hint.setStyleSheet("color: #949ba4; font-size: 11px; margin-left: 22px;")
        vad_layout.addWidget(self.vad_radio)
        vad_layout.addWidget(vad_hint)
        mode_box.addWidget(vad_card, 1)

        ptt_card = QWidget()
        ptt_card.setStyleSheet("""
            QWidget {
                background-color: #2b2d31; border: 1px solid #383a40; border-radius: 6px; padding: 6px;
            }
        """)
        ptt_layout = QVBoxLayout(ptt_card)
        ptt_layout.setContentsMargins(10, 8, 10, 8)
        self.ptt_radio = QRadioButton("Push-to-Talk (PTT)")
        self.ptt_radio.setStyleSheet("""
            QRadioButton {
                color: #ffffff; font-weight: bold; font-size: 13px;
            }
            QRadioButton::indicator {
                width: 16px; height: 16px; border-radius: 8px; border: 2px solid #80848e; background: #1e1f22;
            }
            QRadioButton::indicator:checked {
                background-color: #5865F2; border-color: #5865F2;
            }
        """)
        ptt_hint = QLabel("Transmits only when assigned keybind is held.")
        ptt_hint.setStyleSheet("color: #949ba4; font-size: 11px; margin-left: 22px;")
        ptt_layout.addWidget(self.ptt_radio)
        ptt_layout.addWidget(ptt_hint)
        mode_box.addWidget(ptt_card, 1)

        self.input_mode_group = QButtonGroup(self)
        self.input_mode_group.addButton(self.vad_radio)
        self.input_mode_group.addButton(self.ptt_radio)

        if self.ptt_mode:
            self.ptt_radio.setChecked(True)
        else:
            self.vad_radio.setChecked(True)

        layout.addLayout(mode_box)

        # Push to Talk Keybind Section
        self.ptt_key_container = QWidget()
        ptt_key_l = QHBoxLayout(self.ptt_key_container)
        ptt_key_l.setContentsMargins(0, 4, 0, 4)
        ptt_key_l.setSpacing(10)

        ptt_key_lbl_title = QLabel("Push-to-Talk Keybind:")
        ptt_key_lbl_title.setStyleSheet("color: #dbdee1; font-weight: bold; font-size: 13px;")
        ptt_key_l.addWidget(ptt_key_lbl_title)

        self.ptt_key_badge = QLabel(self.ptt_key)
        self.ptt_key_badge.setStyleSheet("""
            background-color: #1e1f22; color: #5865F2; font-weight: bold;
            font-size: 13px; padding: 6px 14px; border: 1px solid #5865F2; border-radius: 4px;
        """)
        ptt_key_l.addWidget(self.ptt_key_badge)

        self.record_key_btn = QPushButton("⌨️ Record Keybind")
        self.record_key_btn.setStyleSheet("""
            QPushButton {
                background-color: #4e5058; color: white; font-weight: bold;
                padding: 6px 14px; border-radius: 4px; border: none; font-size: 12px;
            }
            QPushButton:hover { background-color: #6d6f78; }
        """)
        self.record_key_btn.clicked.connect(self._start_recording_key)
        ptt_key_l.addWidget(self.record_key_btn)

        self.ptt_combo = QComboBox()
        self.ptt_combo.addItems(["Space", "V", "B", "C", "X", "Caps Lock", "Shift", "Control", "Alt"])
        idx = self.ptt_combo.findText(self.ptt_key)
        if idx >= 0:
            self.ptt_combo.setCurrentIndex(idx)
        self.ptt_combo.setStyleSheet("""
            QComboBox {
                background-color: #1e1f22; color: #ffffff; border: 1px solid #383a40;
                border-radius: 4px; padding: 4px 8px; font-size: 12px;
            }
        """)
        self.ptt_combo.currentTextChanged.connect(self._on_ptt_key_combo_changed)
        ptt_key_l.addWidget(self.ptt_combo)
        ptt_key_l.addStretch(1)

        layout.addWidget(self.ptt_key_container)
        self.ptt_key_container.setVisible(self.ptt_mode)

        self.vad_radio.toggled.connect(self._on_input_mode_changed)
        self.ptt_radio.toggled.connect(self._on_input_mode_changed)

        # 4. Noise Suppression
        self.noise_cb = QCheckBox("Noise Suppression (Noise Gate)")
        self.noise_cb.setChecked(self.noise_suppression)
        self.noise_cb.toggled.connect(lambda chk: self.audio_manager.set_noise_suppression(chk))
        layout.addWidget(self.noise_cb)

        # 5. VAD Threshold slider
        self.vad_lbl = QLabel(f"Voice Sensitivity: {self.audio_manager.vad_threshold:.3f}")
        layout.addWidget(self.vad_lbl)
        self.vad_slider = QSlider(Qt.Orientation.Horizontal)
        self.vad_slider.setRange(2, 50)
        self.vad_slider.setValue(max(2, min(50, int(self.audio_manager.vad_threshold * 1000))))
        self.vad_slider.valueChanged.connect(self._on_vad_thresh)
        layout.addWidget(self.vad_slider)

        # 6. Mic Test
        layout.addWidget(QLabel("MIC TEST:"))
        self.meter_bar = QProgressBar()
        self.meter_bar.setRange(0, 100)
        self.meter_bar.setValue(0)
        self.meter_bar.setTextVisible(False)
        self.meter_bar.setFixedHeight(12)
        self.meter_bar.setStyleSheet("""
            QProgressBar { background-color: #1e1f22; border: none; border-radius: 4px; }
            QProgressBar::chunk { background-color: #23a55a; border-radius: 4px; }
        """)
        layout.addWidget(self.meter_bar)

        self.test_btn = QPushButton("Let's Check")
        self.test_btn.setStyleSheet("""
            background-color: #4e5058; color: white; font-weight: bold;
            padding: 8px; border-radius: 4px; border: none;
        """)
        self.test_btn.clicked.connect(self._toggle_mic_test)
        layout.addWidget(self.test_btn)

        # 7. Screen Share presets
        sep_sc = QFrame()
        sep_sc.setFrameShape(QFrame.Shape.HLine)
        sep_sc.setStyleSheet("background-color: #35373c; margin: 10px 0;")
        layout.addWidget(sep_sc)

        cfg = load_config()
        saved_res = cfg.get("stream_resolution", "720p")
        saved_fps = str(cfg.get("stream_fps", 15))
        saved_q = int(cfg.get("stream_quality", 45))

        layout.addWidget(QLabel("SCREEN SHARE QUALITY & PERFORMANCE:"))
        sc_row = QHBoxLayout()
        sc_row.addWidget(QLabel("Resolution:"))
        self.sc_res_combo = QComboBox()
        self.sc_res_combo.addItems(["480p", "720p", "1080p"])
        if saved_res not in ["480p", "720p", "1080p"]:
            saved_res = "720p"
        self.sc_res_combo.setCurrentText(saved_res)
        sc_row.addWidget(self.sc_res_combo)

        sc_row.addWidget(QLabel("FPS:"))
        self.sc_fps_combo = QComboBox()
        self.sc_fps_combo.addItems(["15", "24", "30"])
        if saved_fps not in ["15", "24", "30"]:
            saved_fps = "30"
        self.sc_fps_combo.setCurrentText(saved_fps)
        sc_row.addWidget(self.sc_fps_combo)


        sc_row.addStretch(1)
        layout.addLayout(sc_row)

        self.sc_q_lbl = QLabel(f"Stream Compression Quality: {saved_q}%")
        layout.addWidget(self.sc_q_lbl)

        self.sc_q_slider = QSlider(Qt.Orientation.Horizontal)
        self.sc_q_slider.setRange(20, 85)
        self.sc_q_slider.setValue(saved_q)
        self.sc_q_slider.valueChanged.connect(self._on_screen_settings_changed)
        layout.addWidget(self.sc_q_slider)

        self.sc_res_combo.currentTextChanged.connect(self._on_screen_settings_changed)
        self.sc_fps_combo.currentTextChanged.connect(self._on_screen_settings_changed)

        layout.addStretch(1)
        scroll.setWidget(w)
        return scroll

    def _start_recording_key(self):
        self._is_recording_key = True
        self.record_key_btn.setText("Press any key...")
        self.record_key_btn.setStyleSheet("""
            QPushButton {
                background-color: #ed4245; color: white; font-weight: bold;
                padding: 6px 14px; border-radius: 4px; border: none; font-size: 12px;
            }
        """)
        self.setFocus()

    def _update_record_btn_ui(self):
        self.record_key_btn.setText("⌨️ Record Keybind")
        self.record_key_btn.setStyleSheet("""
            QPushButton {
                background-color: #4e5058; color: white; font-weight: bold;
                padding: 6px 14px; border-radius: 4px; border: none; font-size: 12px;
            }
            QPushButton:hover { background-color: #6d6f78; }
        """)
        self.ptt_key_badge.setText(self.ptt_key)
        idx = self.ptt_combo.findText(self.ptt_key)
        if idx >= 0:
            self.ptt_combo.setCurrentIndex(idx)

    def _on_ptt_key_combo_changed(self, key_text: str):
        if not self._is_recording_key and key_text:
            self.ptt_key = key_text
            self.ptt_key_badge.setText(self.ptt_key)
            self._on_ptt_key_changed(self.ptt_key)

    def _on_input_mode_changed(self):
        is_ptt = self.ptt_radio.isChecked()
        self.audio_manager.set_ptt_mode(is_ptt)
        if hasattr(self, "ptt_key_container"):
            self.ptt_key_container.setVisible(is_ptt)
        self.ptt_settings_changed.emit(is_ptt, self.ptt_key)
        try:
            cfg = load_config()
            cfg["ptt_mode"] = is_ptt
            save_config(cfg)
        except Exception:
            pass

    def _on_ptt_key_changed(self, key_text: str):
        is_ptt = self.ptt_radio.isChecked()
        self.ptt_key = key_text
        self.ptt_settings_changed.emit(is_ptt, key_text)
        try:
            cfg = load_config()
            cfg["ptt_key"] = key_text
            save_config(cfg)
        except Exception:
            pass

    def _on_screen_settings_changed(self):
        res = self.sc_res_combo.currentText()
        fps = int(self.sc_fps_combo.currentText() or 15)
        q = self.sc_q_slider.value() if hasattr(self, "sc_q_slider") else 45
        if hasattr(self, "sc_q_lbl"):
            self.sc_q_lbl.setText(f"Stream Compression Quality: {q}%")
        self.screen_settings_changed.emit(res, fps, q)
        try:
            cfg = load_config()
            cfg["stream_resolution"] = res
            cfg["stream_fps"] = fps
            cfg["stream_quality"] = q
            save_config(cfg)
        except Exception:
            pass

    def _load_audio_devices(self):
        in_devs = self.audio_manager.get_input_devices()
        self.in_combo.clear()
        self.in_combo.addItem("Default", None)
        for d in in_devs:
            self.in_combo.addItem(f"{d['name']} (ID {d['index']})", d['index'])

        out_devs = self.audio_manager.get_output_devices()
        self.out_combo.clear()
        self.out_combo.addItem("Default", None)
        for d in out_devs:
            self.out_combo.addItem(f"{d['name']} (ID {d['index']})", d['index'])

    def _on_mic_vol(self, val):
        self.mic_lbl.setText(f"Input Volume: {val}%")
        self.audio_manager.mic_volume = val / 100.0

    def _on_out_vol(self, val):
        self.out_lbl.setText(f"Output Volume: {val}%")
        self.audio_manager.output_volume = val / 100.0

    def _on_vad_thresh(self, val):
        thresh = val / 1000.0
        self.vad_lbl.setText(f"Voice Sensitivity: {thresh:.3f}")
        self.audio_manager.vad_threshold = thresh

    def _toggle_mic_test(self):
        self._testing_mic = not self._testing_mic
        if self._testing_mic:
            self.test_btn.setText("Stop Checking")
            self.audio_manager.loopback_test = True

            def intercept(data, speaking, rms):
                self._current_mic_level = rms
                if self._orig_callback:
                    self._orig_callback(data, speaking, rms)

            self.audio_manager.on_mic_frame = intercept
            self.meter_timer.start()
        else:
            self.test_btn.setText("Let's Check")
            self.audio_manager.loopback_test = False
            self.audio_manager.on_mic_frame = self._orig_callback
            self.meter_timer.stop()
            self.meter_bar.setValue(0)

    def _update_meter(self):
        pct = min(100, int(self._current_mic_level * 600))
        self.meter_bar.setValue(pct)

    # ------------------ Page 3: Appearance ------------------

    def _create_appearance_page(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background-color: #313338; }")

        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(30, 24, 30, 24)
        layout.setSpacing(16)

        # 1. Theme Section
        title = QLabel("🎨 Appearance & Themes")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #ffffff;")
        layout.addWidget(title)

        theme_desc = QLabel("Select application theme:")
        theme_desc.setStyleSheet("color: #949ba4; font-size: 13px;")
        layout.addWidget(theme_desc)

        self.theme_group = QButtonGroup(self)

        themes = [
            ("dark", "🌙 Dark (Discord Dark)", "Classic Discord dark theme"),
            ("amoled", "🖤 AMOLED (Pure Black)", "Deep #000000 black for high contrast displays"),
            ("light", "☀️ Light (Discord Light)", "Crisp light user interface theme")
        ]

        for key, name, desc in themes:
            card = QWidget()
            card.setStyleSheet("""
                QWidget {
                    background-color: #2b2d31;
                    border: 1px solid #383a40;
                    border-radius: 8px;
                }
            """)
            c_layout = QHBoxLayout(card)
            c_layout.setContentsMargins(14, 10, 14, 10)

            radio = QRadioButton(name)
            radio.setProperty("theme_key", key)
            radio.setStyleSheet("color: #ffffff; font-weight: bold; font-size: 14px;")
            if self.current_theme == key or (key == "dark" and self.current_theme not in ("amoled", "light")):
                radio.setChecked(True)
            self.theme_group.addButton(radio)
            c_layout.addWidget(radio)

            sub_lbl = QLabel(desc)
            sub_lbl.setStyleSheet("color: #949ba4; font-size: 12px; margin-left: 10px;")
            c_layout.addWidget(sub_lbl, 1)

            layout.addWidget(card)

        self.theme_group.buttonToggled.connect(self._on_theme_toggled)

        # 2. Language Section
        lang_title = QLabel("🌐 Interface Language")
        lang_title.setStyleSheet("font-size: 18px; font-weight: bold; color: #ffffff; margin-top: 14px;")
        layout.addWidget(lang_title)

        lang_desc = QLabel("Select preferred application language:")
        lang_desc.setStyleSheet("color: #949ba4; font-size: 13px;")
        layout.addWidget(lang_desc)

        self.lang_combo = QComboBox()
        self.lang_combo.setStyleSheet("""
            QComboBox {
                background-color: #1e1f22;
                color: #ffffff;
                border: 1px solid #383a40;
                border-radius: 6px;
                padding: 8px 14px;
                font-size: 14px;
                min-height: 24px;
            }
        """)
        self.lang_combo.addItem("🇬🇧 English", "en")
        self.lang_combo.addItem("🇷🇺 Русский (Russian)", "ru")

        idx = 0 if self.current_language == "en" else 1
        self.lang_combo.setCurrentIndex(idx)
        self.lang_combo.currentIndexChanged.connect(self._on_language_changed)
        layout.addWidget(self.lang_combo)

        # 3. Notifications & DND Section
        dnd_title = QLabel("🔕 Notifications & Do Not Disturb")
        dnd_title.setStyleSheet("font-size: 18px; font-weight: bold; color: #ffffff; margin-top: 14px;")
        layout.addWidget(dnd_title)

        dnd_desc = QLabel("Suppress desktop toast notifications:")
        dnd_desc.setStyleSheet("color: #949ba4; font-size: 13px;")
        layout.addWidget(dnd_desc)

        self.dnd_cb = QCheckBox("Do Not Disturb (Disable desktop popups)")
        self.dnd_cb.setStyleSheet("""
            QCheckBox {
                color: #ffffff; font-size: 14px; font-weight: bold; spacing: 8px;
            }
            QCheckBox::indicator {
                width: 18px; height: 18px; border-radius: 4px;
                border: 2px solid #80848e; background-color: #1e1f22;
            }
            QCheckBox::indicator:checked {
                border-color: #f23f43; background-color: #f23f43;
            }
        """)
        self.dnd_cb.setChecked(self.dnd_mode)
        self.dnd_cb.toggled.connect(self._on_dnd_toggled)
        layout.addWidget(self.dnd_cb)

        layout.addStretch(1)
        scroll.setWidget(w)
        return scroll

    def _on_dnd_toggled(self, checked: bool):
        self.dnd_mode = checked
        self.dnd_toggled.emit(checked)
        try:
            cfg = load_config()
            cfg["dnd_mode"] = checked
            save_config(cfg)
        except Exception:
            pass

    def _on_theme_toggled(self, button: QRadioButton, checked: bool):
        if checked:
            theme_key = button.property("theme_key")
            self.current_theme = theme_key
            self.theme_changed.emit(theme_key)
            self._save_theme_and_lang()

    def _on_language_changed(self, index: int):
        lang_key = self.lang_combo.currentData()
        self.current_language = lang_key
        set_language(lang_key)
        self.language_changed.emit(lang_key)
        self._save_theme_and_lang()

    def _save_theme_and_lang(self):
        try:
            cfg = load_config()
            cfg["theme"] = self.current_theme
            cfg["language"] = self.current_language
            save_config(cfg)
        except Exception:
            pass

    def _on_category_changed(self, row: int):
        self.pages.setCurrentIndex(row)

    def keyPressEvent(self, event: QKeyEvent):
        if getattr(self, "_is_recording_key", False):
            key = event.key()
            if key in (Qt.Key.Key_Control, Qt.Key.Key_Shift, Qt.Key.Key_Alt, Qt.Key.Key_Meta):
                return
            if key == Qt.Key.Key_Escape:
                self._is_recording_key = False
                self._update_record_btn_ui()
                event.accept()
                return

            if key == Qt.Key.Key_Space:
                key_text = "Space"
            elif key == Qt.Key.Key_CapsLock:
                key_text = "Caps Lock"
            elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                key_text = "Enter"
            elif key == Qt.Key.Key_Tab:
                key_text = "Tab"
            else:
                seq = QKeySequence(key).toString()
                key_text = seq if seq else event.text().upper()

            if key_text:
                self.ptt_key = key_text
                self._is_recording_key = False
                self._update_record_btn_ui()
                self._on_ptt_key_changed(self.ptt_key)
                event.accept()
                return

        super().keyPressEvent(event)

    def closeEvent(self, event):
        if self._testing_mic:
            self._toggle_mic_test()
        super().closeEvent(event)
