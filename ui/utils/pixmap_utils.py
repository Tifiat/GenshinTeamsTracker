from __future__ import annotations

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen, QPixmap


def trim_transparent_pixmap(
    pixmap: QPixmap,
    *,
    alpha_threshold: int = 0,
) -> QPixmap:
    image = pixmap.toImage()
    if image.isNull():
        return pixmap

    alpha_threshold = max(0, min(255, int(alpha_threshold)))
    left = image.width()
    right = -1
    top = image.height()
    bottom = -1

    for y in range(image.height()):
        for x in range(image.width()):
            if image.pixelColor(x, y).alpha() <= alpha_threshold:
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
    alpha_threshold: int = 0,
) -> QPixmap:
    return scale_trimmed_pixmap_to_size(
        pixmap,
        size,
        size,
        padding=padding,
        alpha_threshold=alpha_threshold,
    )


def scale_trimmed_pixmap_to_size(
    pixmap: QPixmap,
    width: int,
    height: int,
    *,
    padding: int = 0,
    alpha_threshold: int = 0,
) -> QPixmap:
    width = max(1, int(width))
    height = max(1, int(height))
    padding = max(0, int(padding))

    canvas = QPixmap(width, height)
    canvas.fill(Qt.GlobalColor.transparent)

    trimmed = trim_transparent_pixmap(pixmap, alpha_threshold=alpha_threshold)
    if trimmed.isNull():
        return canvas

    content_width = max(1, width - padding * 2)
    content_height = max(1, height - padding * 2)
    scaled = trimmed.scaled(
        content_width,
        content_height,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )

    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.drawPixmap(
        (width - scaled.width()) // 2,
        (height - scaled.height()) // 2,
        scaled,
    )
    painter.end()
    return canvas


def apply_diagonal_alpha_mask(
    pixmap: QPixmap,
    *,
    keep_bottom_left: bool,
    feather: int,
) -> QPixmap:
    """Keep one side of a bottom-left to top-right diagonal.

    ``keep_bottom_left=True`` preserves the lower-left half under the ``/``
    diagonal. Otherwise the complementary top-right half is preserved.
    """
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
            if keep_bottom_left:
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
    bottom_left_pixmap: QPixmap,
    top_right_pixmap: QPixmap,
    *,
    size: int | None = None,
    width: int | None = None,
    height: int | None = None,
    feather: int = 0,
) -> QPixmap:
    """Compose two pixmaps into complementary ``/`` diagonal regions."""
    if size is not None:
        width = size
        height = size
    width = max(1, int(width or 1))
    height = max(1, int(height or 1))

    bottom_left_pixmap = apply_diagonal_alpha_mask(
        bottom_left_pixmap,
        keep_bottom_left=True,
        feather=feather,
    )
    top_right_pixmap = apply_diagonal_alpha_mask(
        top_right_pixmap,
        keep_bottom_left=False,
        feather=feather,
    )

    canvas = QPixmap(width, height)
    canvas.fill(Qt.GlobalColor.transparent)
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.drawPixmap(0, 0, bottom_left_pixmap)
    painter.drawPixmap(0, 0, top_right_pixmap)
    painter.end()
    return canvas


def draw_count_badge(
    pixmap: QPixmap,
    text: str,
    *,
    margin: int = 1,
) -> QPixmap:
    if pixmap.isNull() or not text:
        return pixmap

    canvas = QPixmap(pixmap)
    shortest_side = min(canvas.width(), canvas.height())
    badge_size = min(13, max(8, round(shortest_side * 0.38)))
    badge_rect = QRect(
        canvas.width() - badge_size - margin,
        canvas.height() - badge_size - margin,
        badge_size,
        badge_size,
    )

    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(QPen(QColor("#8f7440"), 1))
    painter.setBrush(QColor("#4a3b22"))
    badge_radius = max(3, badge_size // 3)
    painter.drawRoundedRect(badge_rect, badge_radius, badge_radius)

    font = QFont(painter.font())
    font.setPointSize(max(5, round(shortest_side * 0.24)))
    font.setBold(True)
    painter.setFont(font)
    painter.setPen(QColor("#f0d58a"))
    painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, text)
    painter.end()
    return canvas
