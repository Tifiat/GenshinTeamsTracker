from __future__ import annotations

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QImage, QPainter, QPixmap


def trim_transparent_pixmap(pixmap: QPixmap) -> QPixmap:
    image = pixmap.toImage()
    if image.isNull():
        return pixmap

    left = image.width()
    right = -1
    top = image.height()
    bottom = -1

    for y in range(image.height()):
        for x in range(image.width()):
            if image.pixelColor(x, y).alpha() <= 0:
                continue
            left = min(left, x)
            right = max(right, x)
            top = min(top, y)
            bottom = max(bottom, y)

    if right < left or bottom < top:
        return pixmap

    return pixmap.copy(QRect(left, top, right - left + 1, bottom - top + 1))


def scale_trimmed_pixmap(
    pixmap: QPixmap,
    size: int,
    *,
    padding: int = 0,
) -> QPixmap:
    canvas = QPixmap(size, size)
    canvas.fill(Qt.GlobalColor.transparent)

    trimmed = trim_transparent_pixmap(pixmap)
    if trimmed.isNull():
        return canvas

    content_size = max(1, size - padding * 2)
    scaled = trimmed.scaled(
        content_size,
        content_size,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )

    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.drawPixmap(
        (size - scaled.width()) // 2,
        (size - scaled.height()) // 2,
        scaled,
    )
    painter.end()
    return canvas


def apply_diagonal_alpha(
    pixmap: QPixmap,
    *,
    keep_top_left: bool,
    feather: int,
) -> QPixmap:
    image = pixmap.toImage().convertToFormat(QImage.Format.Format_ARGB32)
    if image.isNull():
        return pixmap

    width = image.width()
    height = image.height()
    denominator_x = max(1, width - 1)
    denominator_y = max(1, height - 1)
    feather_band = max(0.001, feather / max(1, min(width, height)))

    for y in range(height):
        for x in range(width):
            color = image.pixelColor(x, y)
            if color.alpha() <= 0:
                continue

            signed = (x / denominator_x) + (y / denominator_y) - 1.0
            if keep_top_left:
                if signed <= -feather_band:
                    alpha_factor = 1.0
                elif signed >= feather_band:
                    alpha_factor = 0.0
                else:
                    alpha_factor = (feather_band - signed) / (2 * feather_band)
            else:
                if signed >= feather_band:
                    alpha_factor = 1.0
                elif signed <= -feather_band:
                    alpha_factor = 0.0
                else:
                    alpha_factor = (signed + feather_band) / (2 * feather_band)

            color.setAlpha(int(color.alpha() * alpha_factor))
            image.setPixelColor(x, y, color)

    return QPixmap.fromImage(image)


def make_diagonal_split_pixmap(
    bottom_right_pixmap: QPixmap,
    top_left_pixmap: QPixmap,
    *,
    size: int,
    feather: int,
) -> QPixmap:
    top_left_pixmap = apply_diagonal_alpha(
        top_left_pixmap,
        keep_top_left=True,
        feather=feather,
    )

    canvas = QPixmap(size, size)
    canvas.fill(Qt.GlobalColor.transparent)
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.drawPixmap(0, 0, bottom_right_pixmap)
    painter.drawPixmap(0, 0, top_left_pixmap)
    painter.end()
    return canvas
