"""
Avatar rendering helper for VimCord.
Generates smooth antialiased circular avatars from base64 image strings or initials.
"""

import base64
from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QPixmap, QImage, QPainter, QPainterPath, QColor, QFont


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
