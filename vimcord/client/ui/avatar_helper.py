"""
Avatar rendering helper for VimCord.
Generates smooth antialiased circular avatars from base64 image strings or initials.
"""

import base64
from typing import Optional
from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QPixmap, QImage, QPainter, QPainterPath, QColor, QFont, QPen
from PyQt6.QtWidgets import QWidget



def get_round_avatar_pixmap(size: int, initials: str = "U", color_hex: str = "#5865F2", base64_data: str = "") -> QPixmap:
    """
    Renders an antialiased circular avatar pixmap of given diameter.
    If base64_data is valid, crops and scales the image into the circle.
    Otherwise, paints color_hex background with centered white initials text.
    """
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

    path = QPainterPath()
    path.addEllipse(0, 0, size, size)
    painter.setClipPath(path)

    loaded_img = False
    if base64_data and len(base64_data) > 10:
        try:
            clean_b64 = base64_data
            if "," in clean_b64:
                clean_b64 = clean_b64.split(",", 1)[1]
            raw_bytes = base64.b64decode(clean_b64)
            img = QImage()
            if img.loadFromData(raw_bytes):
                scaled = img.scaled(
                    size, size,
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation
                )
                sx = max(0, (scaled.width() - size) // 2)
                sy = max(0, (scaled.height() - size) // 2)
                painter.drawImage(0, 0, scaled, sx, sy, size, size)
                loaded_img = True
        except Exception:
            loaded_img = False

    if not loaded_img:
        bg_col = color_hex if color_hex and color_hex.startswith("#") else "#5865F2"
        painter.fillPath(path, QColor(bg_col))
        painter.setPen(QColor("#ffffff"))
        font_size = max(10, int(size * 0.38))
        font = QFont("Segoe UI", font_size, QFont.Weight.Bold)
        painter.setFont(font)
        display_initials = (initials or "U")[:2].upper()
        painter.drawText(QRectF(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, display_initials)

    painter.end()
    return pixmap


class RoundAvatarWidget(QWidget):
    """
    Modern antialiased circular avatar widget.
    Avoids QSS border-radius / QPixmap clipping quirks and renders smooth,
    pixel-perfect circular avatars with an outer voice-activity green ring.
    """

    def __init__(self, size: int = 36, parent=None):
        super().__init__(parent)
        self._size = size
        self.setFixedSize(size, size)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        self._initials = "U"
        self._color_hex = "#5865F2"
        self._base64_data = ""
        self._is_speaking = False
        self._cached_pixmap: Optional[QPixmap] = None

    def set_user_data(self, initials: str = "U", color_hex: str = "#5865F2", base64_data: str = ""):
        dirty = (
            self._initials != initials or
            self._color_hex != color_hex or
            self._base64_data != base64_data
        )
        if dirty:
            self._initials = initials or "U"
            self._color_hex = color_hex or "#5865F2"
            self._base64_data = base64_data or ""
            self._cached_pixmap = None
            self.update()

    def set_speaking(self, is_speaking: bool):
        if self._is_speaking != is_speaking:
            self._is_speaking = bool(is_speaking)
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        s = float(self._size)
        # Ring zone: outer margin
        ring_pad = 1.5
        ring_rect = QRectF(ring_pad, ring_pad, s - ring_pad * 2, s - ring_pad * 2)

        # Draw green active speaking halo
        if self._is_speaking:
            pen = QPen(QColor("#23a55a"))
            pen.setWidthF(2.5)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(ring_rect)

        # Inner avatar circle (3px inset ensures spacing from green ring)
        inner_inset = 3.5
        avatar_rect = QRectF(inner_inset, inner_inset, s - inner_inset * 2, s - inner_inset * 2)
        inner_size = int(avatar_rect.width())

        # Render cached avatar pixmap at inner_size
        if self._cached_pixmap is None or self._cached_pixmap.width() != inner_size:
            self._cached_pixmap = get_round_avatar_pixmap(
                inner_size,
                initials=self._initials,
                color_hex=self._color_hex,
                base64_data=self._base64_data
            )

        if self._cached_pixmap:
            painter.drawPixmap(int(avatar_rect.x()), int(avatar_rect.y()), self._cached_pixmap)

        painter.end()

