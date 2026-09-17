"""
Comprehensive Discord-style Settings and Account Management Dialog.
Overhauled with Discord Dark aesthetic, profile banner, bio editor,
Voice Activity (VAD) / Push-to-Talk (PTT), Noise Gate toggle, and Screen Share presets.
"""

from typing import Dict, Any, Optional
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QSlider, QProgressBar, QStackedWidget,
    QListWidget, QListWidgetItem, QFrame, QMessageBox, QFileDialog,
    QRadioButton, QCheckBox, QScrollArea
)
import base64
from vimcord.client.audio.audio_manager import AudioManager
from vimcord.client.ui.avatar_helper import get_round_avatar_pixmap


class SettingsDialog(QDialog):
    profile_updated = pyqtSignal(str, str, str, str, str)  # username, status_text, avatar_color, avatar_image, bio
    password_changed = pyqtSignal(str, str)                 # old_pass, new_pass
    logout_requested = pyqtSignal()
    screen_settings_changed = pyqtSignal(str, int, int)     # resolution, fps, quality
    ptt_settings_changed = pyqtSignal(bool, str)            # ptt_mode, ptt_key

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
        self.user_id = user_data.get("user_id", "")
        self.status_text = user_data.get("status_text", "В сети")
        self.avatar_color = user_data.get("avatar_color", "#5865F2")
        self.avatar_image = user_data.get("avatar_image", "")
        self.bio = user_data.get("bio", "")
        self.selected_color = self.avatar_color

        self.ptt_mode = getattr(self.audio_manager, "ptt_mode", False)
        self.ptt_key = getattr(parent, "ptt_key", "Space") if parent else "Space"
        self.noise_suppression = getattr(self.audio_manager, "noise_suppression", True)

        self.setWindowTitle("Настройки — VimCord")
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

        header_usr = QLabel("НАСТРОЙКИ ПОЛЬЗОВАТЕЛЯ")
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
        self.nav_list.addItem("👤 Мой аккаунт")
        self.nav_list.addItem("🎙️ Голос и видео")
        self.nav_list.addItem("🎨 Внешний вид")
        self.nav_list.currentRowChanged.connect(self._on_category_changed)
        sb_layout.addWidget(self.nav_list)

        sb_layout.addStretch(1)

        # Logout button
        logout_btn = QPushButton("Выйти из аккаунта")
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

        title = QLabel("Моя учетная запись")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #ffffff;")
        layout.addWidget(title)

        # Profile Card Banner
        card = QWidget()
        card.setStyleSheet("background-color: #1e1f22; border-radius: 8px; padding: 14px;")
        c_layout = QHBoxLayout(card)
        c_layout.setSpacing(16)

        self.avatar_preview = QLabel()
        self.avatar_preview.setFixedSize(54, 54)
        self.avatar_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._refresh_avatar_preview()
        c_layout.addWidget(self.avatar_preview)

        info_l = QVBoxLayout()
        info_l.setSpacing(2)
        self.card_name_lbl = QLabel(self.username)
        self.card_name_lbl.setStyleSheet("color: #ffffff; font-size: 16px; font-weight: bold;")
        info_l.addWidget(self.card_name_lbl)

        id_lbl = QLabel(f"ID: {self.user_id}")
        id_lbl.setStyleSheet("color: #949ba4; font-size: 11px;")
        info_l.addWidget(id_lbl)

        self.card_status_lbl = QLabel(self.status_text)
        self.card_status_lbl.setStyleSheet("color: #23a55a; font-size: 12px;")
        info_l.addWidget(self.card_status_lbl)
        c_layout.addLayout(info_l, 1)

        layout.addWidget(card)

        # Avatar Upload / Remove Row
        av_btns_row = QHBoxLayout()
        av_btns_row.setSpacing(10)

        upload_av_btn = QPushButton("📁 Загрузить аватарку (PNG/JPG)")
        upload_av_btn.setStyleSheet("""
            QPushButton {
                background-color: #4e5058; color: white; font-weight: bold;
                padding: 6px 12px; border-radius: 4px; border: none; font-size: 12px;
            }
            QPushButton:hover { background-color: #6d6f78; }
        """)
        upload_av_btn.clicked.connect(self._on_upload_avatar)
        av_btns_row.addWidget(upload_av_btn)

        remove_av_btn = QPushButton("✕ Сбросить на цвет")
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
        layout.addWidget(QLabel("ОТОБРАЖАЕМОЕ ИМЯ:"))
        self.uname_edit = QLineEdit(self.username)
        self.uname_edit.setStyleSheet("background-color: #1e1f22; color: #ffffff; padding: 8px; border-radius: 4px; border: none;")
        layout.addWidget(self.uname_edit)

        layout.addWidget(QLabel("СТАТУС:"))
        self.status_edit = QLineEdit(self.status_text)
        self.status_edit.setPlaceholderText("Например: Кодит на Python, Играет...")
        self.status_edit.setStyleSheet("background-color: #1e1f22; color: #ffffff; padding: 8px; border-radius: 4px; border: none;")
        layout.addWidget(self.status_edit)

        layout.addWidget(QLabel("О СЕБЕ (BIO):"))
        self.bio_edit = QLineEdit(self.bio)
        self.bio_edit.setPlaceholderText("Расскажите о себе (отображается в профиле)...")
        self.bio_edit.setStyleSheet("background-color: #1e1f22; color: #ffffff; padding: 8px; border-radius: 4px; border: none;")
        layout.addWidget(self.bio_edit)

        # Avatar color palette
        layout.addWidget(QLabel("ЦВЕТ АВАТАРА (ДЛЯ СТАНДАРТНОЙ ИКОНКИ):"))
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

        save_prof_btn = QPushButton("Сохранить изменения профиля")
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

        pw_title = QLabel("СМЕНА ПАРОЛЯ:")
        pw_title.setStyleSheet("color: #b5bac1; font-weight: bold; font-size: 11px;")
        layout.addWidget(pw_title)

        pw_row = QHBoxLayout()
        self.old_pw_edit = QLineEdit()
        self.old_pw_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.old_pw_edit.setPlaceholderText("Текущий пароль")
        self.old_pw_edit.setStyleSheet("background-color: #1e1f22; color: #ffffff; padding: 8px; border-radius: 4px; border: none;")
        pw_row.addWidget(self.old_pw_edit)

        self.new_pw_edit = QLineEdit()
        self.new_pw_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.new_pw_edit.setPlaceholderText("Новый пароль (от 4 симв.)")
        self.new_pw_edit.setStyleSheet("background-color: #1e1f22; color: #ffffff; padding: 8px; border-radius: 4px; border: none;")
        pw_row.addWidget(self.new_pw_edit)

        change_pw_btn = QPushButton("Обновить пароль")
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

    def _refresh_avatar_preview(self):
        pixmap = get_round_avatar_pixmap(
            54, self.username, self.selected_color, self.avatar_image
        )
        self.avatar_preview.setPixmap(pixmap)

    def _on_upload_avatar(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Выберите изображение профиля", "",
            "Изображения (*.png *.jpg *.jpeg *.bmp *.webp)"
        )
        if not file_path:
            return
        try:
            with open(file_path, "rb") as f:
                raw = f.read()
            if len(raw) > 1024 * 1024:
                QMessageBox.warning(self, "Большой файл", "Пожалуйста, выберите изображение размером до 1 МБ.")
                return
            b64 = base64.b64encode(raw).decode("utf-8")
            self.avatar_image = b64
            self._refresh_avatar_preview()
            QMessageBox.information(self, "Аватарка выбрана", "Аватарка загружена! Нажмите 'Сохранить изменения профиля' для применения.")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка загрузки", f"Не удалось прочитать файл: {e}")

    def _on_remove_avatar(self):
        self.avatar_image = ""
        self._refresh_avatar_preview()

    def _select_avatar_color(self, hex_code: str):
        self.selected_color = hex_code
        self._refresh_avatar_preview()
        for btn, h in self.color_buttons:
            border = "2px solid #ffffff" if h == hex_code else "none"
            btn.setStyleSheet(f"background-color: {h}; border-radius: 14px; border: {border};")

    def _on_save_profile(self):
        new_name = self.uname_edit.text().strip()
        new_status = self.status_edit.text().strip()
        new_bio = self.bio_edit.text().strip()

        if not new_name:
            QMessageBox.warning(self, "Ошибка", "Имя пользователя не может быть пустым!")
            return

        self.username = new_name
        self.status_text = new_status
        self.bio = new_bio
        self.avatar_color = self.selected_color

        self.card_name_lbl.setText(new_name)
        self.card_status_lbl.setText(new_status or "В сети")

        self.profile_updated.emit(new_name, new_status, self.selected_color, self.avatar_image, new_bio)
        QMessageBox.information(self, "Успешно", "Запрос на обновление профиля отправлен на сервер!")

    def _on_change_password(self):
        old_p = self.old_pw_edit.text().strip()
        new_p = self.new_pw_edit.text().strip()
        if not old_p or not new_p:
            QMessageBox.warning(self, "Ошибка", "Заполните оба поля пароля!")
            return
        if len(new_p) < 4:
            QMessageBox.warning(self, "Ошибка", "Новый пароль должен содержать не менее 4 символов!")
            return

        self.password_changed.emit(old_p, new_p)
        self.old_pw_edit.clear()
        self.new_pw_edit.clear()

    def _on_logout(self):
        ret = QMessageBox.question(
            self, "Выход", "Вы действительно хотите выйти из аккаунта?",
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

        title = QLabel("Настройки звука и видео")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #ffffff;")
        layout.addWidget(title)

        # 1. Devices
        layout.addWidget(QLabel("УСТРОЙСТВО ВВОДА (МИКРОФОН):"))
        self.in_combo = QComboBox()
        self.in_combo.currentIndexChanged.connect(lambda idx: self.audio_manager.set_input_device(self.in_combo.currentData()))
        layout.addWidget(self.in_combo)

        layout.addWidget(QLabel("УСТРОЙСТВО ВЫВОДА (ДИНАМИКИ):"))
        self.out_combo = QComboBox()
        self.out_combo.currentIndexChanged.connect(lambda idx: self.audio_manager.set_output_device(self.out_combo.currentData()))
        layout.addWidget(self.out_combo)

        # 2. Volumes
        self.mic_lbl = QLabel(f"Громкость микрофона: {int(self.audio_manager.mic_volume * 100)}%")
        layout.addWidget(self.mic_lbl)
        self.mic_slider = QSlider(Qt.Orientation.Horizontal)
        self.mic_slider.setRange(0, 200)
        self.mic_slider.setValue(int(self.audio_manager.mic_volume * 100))
        self.mic_slider.valueChanged.connect(self._on_mic_vol)
        layout.addWidget(self.mic_slider)

        self.out_lbl = QLabel(f"Громкость звука: {int(self.audio_manager.output_volume * 100)}%")
        layout.addWidget(self.out_lbl)
        self.out_slider = QSlider(Qt.Orientation.Horizontal)
        self.out_slider.setRange(0, 200)
        self.out_slider.setValue(int(self.audio_manager.output_volume * 100))
        self.out_slider.valueChanged.connect(self._on_out_vol)
        layout.addWidget(self.out_slider)

        # 3. Input Mode: VAD vs PTT
        layout.addWidget(QLabel("РЕЖИМ ВВОДА:"))
        mode_box = QHBoxLayout()
        self.vad_radio = QRadioButton("Активация по голосу (VAD)")
        self.ptt_radio = QRadioButton("Режим рации (Push-to-Talk)")
        if self.ptt_mode:
            self.ptt_radio.setChecked(True)
        else:
            self.vad_radio.setChecked(True)

        mode_box.addWidget(self.vad_radio)
        mode_box.addWidget(self.ptt_radio)
        mode_box.addStretch(1)
        layout.addLayout(mode_box)

        # Hotkey row
        key_row = QHBoxLayout()
        key_row.addWidget(QLabel("Клавиша Push-to-Talk:"))
        self.ptt_combo = QComboBox()
        self.ptt_combo.addItems(["Space", "V", "B", "C", "X", "Caps Lock"])
        idx = self.ptt_combo.findText(self.ptt_key)
        if idx >= 0:
            self.ptt_combo.setCurrentIndex(idx)
        key_row.addWidget(self.ptt_combo)
        key_row.addStretch(1)
        layout.addLayout(key_row)

        self.vad_radio.toggled.connect(self._on_input_mode_changed)
        self.ptt_combo.currentTextChanged.connect(self._on_ptt_key_changed)

        # 4. Noise Suppression
        self.noise_cb = QCheckBox("Шумоподавление (Noise Gate)")
        self.noise_cb.setChecked(self.noise_suppression)
        self.noise_cb.toggled.connect(lambda chk: self.audio_manager.set_noise_suppression(chk))
        layout.addWidget(self.noise_cb)

        # 5. VAD Threshold slider
        self.vad_lbl = QLabel(f"Порог активации по голосу: {self.audio_manager.vad_threshold:.3f}")
        layout.addWidget(self.vad_lbl)
        self.vad_slider = QSlider(Qt.Orientation.Horizontal)
        self.vad_slider.setRange(2, 50)
        self.vad_slider.setValue(max(2, min(50, int(self.audio_manager.vad_threshold * 1000))))
        self.vad_slider.valueChanged.connect(self._on_vad_thresh)
        layout.addWidget(self.vad_slider)

        # 6. Mic Test
        layout.addWidget(QLabel("ПРОВЕРКА МИКРОФОНА:"))
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

        self.test_btn = QPushButton("Начать проверку микрофона")
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

        layout.addWidget(QLabel("ДЕМОНСТРАЦИЯ ЭКРАНА (SCREEN SHARE):"))
        sc_row = QHBoxLayout()
        sc_row.addWidget(QLabel("Разрешение:"))
        self.sc_res_combo = QComboBox()
        self.sc_res_combo.addItems(["360p", "480p", "720p", "1080p"])
        self.sc_res_combo.setCurrentText("720p")
        sc_row.addWidget(self.sc_res_combo)

        sc_row.addWidget(QLabel("FPS:"))
        self.sc_fps_combo = QComboBox()
        self.sc_fps_combo.addItems(["10", "15", "20", "30"])
        self.sc_fps_combo.setCurrentText("15")
        sc_row.addWidget(self.sc_fps_combo)

        sc_row.addStretch(1)
        layout.addLayout(sc_row)

        self.sc_res_combo.currentTextChanged.connect(self._on_screen_settings_changed)
        self.sc_fps_combo.currentTextChanged.connect(self._on_screen_settings_changed)

        layout.addStretch(1)
        scroll.setWidget(w)
        return scroll

    def _on_input_mode_changed(self):
        is_ptt = self.ptt_radio.isChecked()
        self.audio_manager.set_ptt_mode(is_ptt)
        self.ptt_settings_changed.emit(is_ptt, self.ptt_combo.currentText())

    def _on_ptt_key_changed(self, key_text: str):
        is_ptt = self.ptt_radio.isChecked()
        self.ptt_settings_changed.emit(is_ptt, key_text)

    def _on_screen_settings_changed(self):
        res = self.sc_res_combo.currentText()
        fps = int(self.sc_fps_combo.currentText() or 15)
        self.screen_settings_changed.emit(res, fps, 45)

    def _load_audio_devices(self):
        in_devs = self.audio_manager.get_input_devices()
        self.in_combo.clear()
        self.in_combo.addItem("По умолчанию", None)
        for d in in_devs:
            self.in_combo.addItem(f"{d['name']} (ID {d['index']})", d['index'])

        out_devs = self.audio_manager.get_output_devices()
        self.out_combo.clear()
        self.out_combo.addItem("По умолчанию", None)
        for d in out_devs:
            self.out_combo.addItem(f"{d['name']} (ID {d['index']})", d['index'])

    def _on_mic_vol(self, val):
        self.mic_lbl.setText(f"Громкость микрофона: {val}%")
        self.audio_manager.mic_volume = val / 100.0

    def _on_out_vol(self, val):
        self.out_lbl.setText(f"Громкость звука: {val}%")
        self.audio_manager.output_volume = val / 100.0

    def _on_vad_thresh(self, val):
        thresh = val / 1000.0
        self.vad_lbl.setText(f"Порог активации по голосу: {thresh:.3f}")
        self.audio_manager.vad_threshold = thresh

    def _toggle_mic_test(self):
        self._testing_mic = not self._testing_mic
        if self._testing_mic:
            self.test_btn.setText("Остановить проверку")
            self.audio_manager.loopback_test = True

            def intercept(data, speaking, rms):
                self._current_mic_level = rms
                if self._orig_callback:
                    self._orig_callback(data, speaking, rms)

            self.audio_manager.on_mic_frame = intercept
            self.meter_timer.start()
        else:
            self.test_btn.setText("Начать проверку микрофона")
            self.audio_manager.loopback_test = False
            self.audio_manager.on_mic_frame = self._orig_callback
            self.meter_timer.stop()
            self.meter_bar.setValue(0)

    def _update_meter(self):
        pct = min(100, int(self._current_mic_level * 600))
        self.meter_bar.setValue(pct)

    # ------------------ Page 3: Appearance ------------------

    def _create_appearance_page(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(30, 24, 30, 24)
        layout.setSpacing(14)

        title = QLabel("Внешний вид")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #ffffff;")
        layout.addWidget(title)

        desc = QLabel("Тема интерфейса: Тёмная (Discord Dark).")
        desc.setStyleSheet("color: #dbdee1; font-size: 14px;")
        layout.addWidget(desc)

        theme_card = QWidget()
        theme_card.setStyleSheet("background-color: #1e1f22; border: 2px solid #5865F2; border-radius: 8px; padding: 16px;")
        tc_layout = QVBoxLayout(theme_card)
        tc_layout.addWidget(QLabel("✔ Тёмная тема активна (Discord Dark #313338 / #1e1f22)"))
        layout.addWidget(theme_card)

        layout.addStretch(1)
        return w

    def _on_category_changed(self, row: int):
        self.pages.setCurrentIndex(row)

    def closeEvent(self, event):
        if self._testing_mic:
            self._toggle_mic_test()
        super().closeEvent(event)
