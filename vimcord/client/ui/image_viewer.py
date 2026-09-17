"""
Full-size Image Viewer Modal Dialog for VimCord.
Allows viewing high-resolution chat photos and saving them to disk.
"""

import base64
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFileDialog, QMessageBox
)
from PyQt6.QtGui import QPixmap, QImage, QIcon
from PyQt6.QtCore import Qt, QByteArray


class ImageViewerModal(QDialog):
    def __init__(self, base64_image: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Просмотр изображения — VimCord")
        self.resize(850, 650)
        self.setStyleSheet("""
            QDialog {
                background-color: #1e1f22;
            }
            QLabel {
                color: #dbdee1;
            }
            QPushButton {
                background-color: #2b2d31;
                color: #dbdee1;
                border: 1px solid #35373c;
                border-radius: 4px;
                padding: 6px 14px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #35373c;
                color: #ffffff;
            }
            QPushButton#saveBtn {
                background-color: #5865F2;
                border: none;
                color: #ffffff;
            }
            QPushButton#saveBtn:hover {
                background-color: #4752c4;
            }
        """)

        self.pixmap = QPixmap()
        try:
            raw_bytes = base64.b64decode(base64_image)
            self.pixmap.loadFromData(raw_bytes)
        except Exception:
            pass

        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Image scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background-color: #111214; border: 1px solid #2b2d31; border-radius: 6px;")

        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if not self.pixmap.isNull():
            # Initial fit within reasonable bounds
            scaled = self.pixmap.scaled(
                800, 560,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.image_label.setPixmap(scaled)
        else:
            self.image_label.setText("Не удалось загрузить изображение.")

        scroll.setWidget(self.image_label)
        layout.addWidget(scroll, 1)

        # Bottom actions
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        info_lbl = QLabel(f"Размер: {self.pixmap.width()} x {self.pixmap.height()} px" if not self.pixmap.isNull() else "")
        info_lbl.setStyleSheet("color: #949ba4; font-size: 12px;")
        btn_layout.addWidget(info_lbl)

        btn_layout.addStretch(1)

        save_btn = QPushButton("💾 Сохранить...")
        save_btn.setObjectName("saveBtn")
        save_btn.clicked.connect(self._save_image)
        btn_layout.addWidget(save_btn)

        close_btn = QPushButton("Закрыть")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)

        layout.addLayout(btn_layout)

    def _save_image(self):
        if self.pixmap.isNull():
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Сохранить изображение",
            "vimcord_image.png",
            "PNG Image (*.png);;JPEG Image (*.jpg *.jpeg);;All Files (*)"
        )
        if path:
            try:
                self.pixmap.save(path)
                QMessageBox.information(self, "Успех", "Изображение успешно сохранено!")
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить: {e}")
