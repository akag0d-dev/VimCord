"""
Audio settings dialog: devices selection, volume levels, VAD threshold, and mic test.
"""

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QSlider, QPushButton, QProgressBar, QGroupBox
)
from vimcord.client.audio.audio_manager import AudioManager


class SettingsDialog(QDialog):
    def __init__(self, audio_manager: AudioManager, parent=None):
        super().__init__(parent)
        self.audio_manager = audio_manager

        self.setWindowTitle("Настройки звука — VimCord")
        self.setFixedSize(460, 480)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        self._testing_mic = False
        self._current_mic_level = 0.0

        # Hook mic frame callback during test
        self._orig_callback = self.audio_manager.on_mic_frame

        self._init_ui()
        self._load_devices()

        self.meter_timer = QTimer(self)
        self.meter_timer.setInterval(40)
        self.meter_timer.timeout.connect(self._update_meter)

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        title = QLabel("⚙️ Настройки звука и голоса")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #ffffff;")
        layout.addWidget(title)

        # 1. Devices Group
        dev_group = QGroupBox("Устройства ввода и вывода")
        dev_group.setStyleSheet("color: #b5bac1; font-weight: bold;")
        dev_layout = QVBoxLayout(dev_group)
        dev_layout.setSpacing(10)

        # Input device
        dev_layout.addWidget(QLabel("УСТРОЙСТВО ВВОДА (МИКРОФОН):"))
        self.input_combo = QComboBox()
        self.input_combo.currentIndexChanged.connect(self._on_input_device_changed)
        dev_layout.addWidget(self.input_combo)

        # Output device
        dev_layout.addWidget(QLabel("УСТРОЙСТВО ВЫВОДА (ДИНАМИКИ):"))
        self.output_combo = QComboBox()
        self.output_combo.currentIndexChanged.connect(self._on_output_device_changed)
        dev_layout.addWidget(self.output_combo)

        layout.addWidget(dev_group)

        # 2. Volume & Sensitivity Group
        vol_group = QGroupBox("Громкость и чувствительность")
        vol_group.setStyleSheet("color: #b5bac1; font-weight: bold;")
        vol_layout = QVBoxLayout(vol_group)
        vol_layout.setSpacing(10)

        # Mic volume
        self.mic_vol_lbl = QLabel(f"Громкость микрофона: {int(self.audio_manager.mic_volume * 100)}%")
        vol_layout.addWidget(self.mic_vol_lbl)
        self.mic_slider = QSlider(Qt.Orientation.Horizontal)
        self.mic_slider.setRange(0, 200)
        self.mic_slider.setValue(int(self.audio_manager.mic_volume * 100))
        self.mic_slider.valueChanged.connect(self._on_mic_volume_changed)
        vol_layout.addWidget(self.mic_slider)

        # Output volume
        self.out_vol_lbl = QLabel(f"Громкость звука: {int(self.audio_manager.output_volume * 100)}%")
        vol_layout.addWidget(self.out_vol_lbl)
        self.out_slider = QSlider(Qt.Orientation.Horizontal)
        self.out_slider.setRange(0, 200)
        self.out_slider.setValue(int(self.audio_manager.output_volume * 100))
        self.out_slider.valueChanged.connect(self._on_out_volume_changed)
        vol_layout.addWidget(self.out_slider)

        # VAD threshold
        self.vad_lbl = QLabel(f"Порог активации по голосу: {int(self.audio_manager.vad_threshold * 1000)}")
        vol_layout.addWidget(self.vad_lbl)
        self.vad_slider = QSlider(Qt.Orientation.Horizontal)
        self.vad_slider.setRange(5, 100)
        self.vad_slider.setValue(int(self.audio_manager.vad_threshold * 1000))
        self.vad_slider.valueChanged.connect(self._on_vad_threshold_changed)
        vol_layout.addWidget(self.vad_slider)

        layout.addWidget(vol_group)

        # 3. Mic Test
        test_group = QGroupBox("Проверка микрофона")
        test_group.setStyleSheet("color: #b5bac1; font-weight: bold;")
        test_layout = QVBoxLayout(test_group)
        test_layout.setSpacing(8)

        self.meter_bar = QProgressBar()
        self.meter_bar.setRange(0, 100)
        self.meter_bar.setValue(0)
        self.meter_bar.setTextVisible(False)
        self.meter_bar.setStyleSheet("""
            QProgressBar {
                background-color: #1e1f22;
                border: 1px solid #3f4147;
                border-radius: 4px;
                height: 12px;
            }
            QProgressBar::chunk {
                background-color: #23a55a;
                border-radius: 3px;
            }
        """)
        test_layout.addWidget(self.meter_bar)

        self.test_btn = QPushButton("Начать проверку микрофона")
        self.test_btn.setProperty("class", "secondary_btn")
        self.test_btn.clicked.connect(self._toggle_mic_test)
        test_layout.addWidget(self.test_btn)

        layout.addWidget(test_group)

        # Close button
        btn_layout = QHBoxLayout()
        btn_layout.addStretch(1)
        close_btn = QPushButton("Готово")
        close_btn.setProperty("class", "primary_btn")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

    def _load_devices(self):
        # Input devices
        in_devs = self.audio_manager.get_input_devices()
        self.input_combo.clear()
        self.input_combo.addItem("По умолчанию", None)
        for d in in_devs:
            self.input_combo.addItem(f"{d['name']} (ID {d['index']})", d['index'])

        # Output devices
        out_devs = self.audio_manager.get_output_devices()
        self.output_combo.clear()
        self.output_combo.addItem("По умолчанию", None)
        for d in out_devs:
            self.output_combo.addItem(f"{d['name']} (ID {d['index']})", d['index'])

    def _on_input_device_changed(self, idx):
        dev_idx = self.input_combo.currentData()
        self.audio_manager.set_input_device(dev_idx)

    def _on_output_device_changed(self, idx):
        dev_idx = self.output_combo.currentData()
        self.audio_manager.set_output_device(dev_idx)

    def _on_mic_volume_changed(self, val):
        self.mic_vol_lbl.setText(f"Громкость микрофона: {val}%")
        self.audio_manager.mic_volume = val / 100.0

    def _on_out_volume_changed(self, val):
        self.out_vol_lbl.setText(f"Громкость звука: {val}%")
        self.audio_manager.output_volume = val / 100.0

    def _on_vad_threshold_changed(self, val):
        self.vad_lbl.setText(f"Порог активации по голосу: {val}")
        self.audio_manager.vad_threshold = val / 1000.0

    def _toggle_mic_test(self):
        self._testing_mic = not self._testing_mic
        if self._testing_mic:
            self.test_btn.setText("Остановить проверку")
            self.audio_manager.loopback_test = True
            
            # Wrapper to intercept RMS
            def interceptor(data, speaking, rms):
                self._current_mic_level = rms
                if self._orig_callback:
                    self._orig_callback(data, speaking, rms)

            self.audio_manager.on_mic_frame = interceptor
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

    def closeEvent(self, event):
        if self._testing_mic:
            self._toggle_mic_test()
        super().closeEvent(event)
