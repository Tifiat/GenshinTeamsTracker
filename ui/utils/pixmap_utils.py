from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen, QPixmap

from ui.utils.hidpi_pixmap import (
    effective_pixmap_dpr,
    logical_pixmap_size,
    make_hidpi_canvas,
    physical_size_for_logical,
)

COUNT_BADGE_BORDER_COLOR = "#8f7440"
COUNT_BADGE_BACKGROUND_COLOR = "#4a3b22"
COUNT_BADGE_TEXT_COLOR = "#f0d58a"
COUNT_BADGE_BORDER_WIDTH = 1
COUNT_BADGE_MARGIN = 1


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
    dpr: float = 1.0,
) -> QPixmap:
    return scale_trimmed_pixmap_to_size(
        pixmap,
        size,
        size,
        padding=padding,
        alpha_threshold=alpha_threshold,
        dpr=dpr,
    )


def scale_trimmed_pixmap_to_size(
    pixmap: QPixmap,
    width: int,
    height: int,
    *,
    padding: int = 0,
    alpha_threshold: int = 0,
    dpr: float = 1.0,
) -> QPixmap:
    width = max(1, int(width))
    height = max(1, int(height))
    padding = max(0, int(padding))
    effective_dpr = effective_pixmap_dpr(dpr)

    canvas = make_hidpi_canvas(QSize(width, height), effective_dpr)

    trimmed = trim_transparent_pixmap(pixmap, alpha_threshold=alpha_threshold)
    if trimmed.isNull():
        return canvas

    content_width = max(1, width - padding * 2)
    content_height = max(1, height - padding * 2)
    physical_content_size = physical_size_for_logical(
        QSize(content_width, content_height),
        effective_dpr,
    )
    scaled = trimmed.scaled(
        physical_content_size,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    scaled.setDevicePixelRatio(effective_dpr)
    scaled_size = logical_pixmap_size(scaled)

    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.drawPixmap(
        (width - scaled_size.width()) // 2,
        (height - scaled_size.height()) // 2,
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

    result = QPixmap.fromImage(image)
    result.setDevicePixelRatio(pixmap.devicePixelRatio())
    return result


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
    dpr = max(
        effective_pixmap_dpr(bottom_left_pixmap.devicePixelRatio()),
        effective_pixmap_dpr(top_right_pixmap.devicePixelRatio()),
    )

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

    canvas = make_hidpi_canvas(QSize(width, height), dpr)
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.drawPixmap(QRect(0, 0, width, height), bottom_left_pixmap)
    painter.drawPixmap(QRect(0, 0, width, height), top_right_pixmap)
    painter.end()
    return canvas


def count_badge_style_cache_key() -> dict[str, str | int]:
    return {
        "border": COUNT_BADGE_BORDER_COLOR,
        "border_width": COUNT_BADGE_BORDER_WIDTH,
        "background": COUNT_BADGE_BACKGROUND_COLOR,
        "text": COUNT_BADGE_TEXT_COLOR,
        "margin": COUNT_BADGE_MARGIN,
    }


def draw_count_badge(
    pixmap: QPixmap,
    text: str,
    *,
    margin: int = COUNT_BADGE_MARGIN,
) -> QPixmap:
    if pixmap.isNull() or not text:
        return pixmap

    canvas = QPixmap(pixmap)
    logical_size = logical_pixmap_size(canvas)
    shortest_side = min(logical_size.width(), logical_size.height())
    badge_size = min(13, max(8, round(shortest_side * 0.38)))
    badge_rect = QRect(
        logical_size.width() - badge_size - margin,
        logical_size.height() - badge_size - margin,
        badge_size,
        badge_size,
    )

    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(QPen(QColor(COUNT_BADGE_BORDER_COLOR), COUNT_BADGE_BORDER_WIDTH))
    painter.setBrush(QColor(COUNT_BADGE_BACKGROUND_COLOR))
    badge_radius = max(3, badge_size // 3)
    painter.drawRoundedRect(badge_rect, badge_radius, badge_radius)

    font = QFont(painter.font())
    font.setPointSize(max(5, round(shortest_side * 0.24)))
    font.setBold(True)
    painter.setFont(font)
    painter.setPen(QColor(COUNT_BADGE_TEXT_COLOR))
    painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, text)
    painter.end()
    return canvas


def pixmap_cache_key_digest(cache_key: Any) -> str:
    payload = json.dumps(
        cache_key,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def persistent_pixmap_cache_path(cache_dir: Path, cache_key: Any) -> Path:
    return cache_dir / f"{pixmap_cache_key_digest(cache_key)}.png"


def load_persistent_pixmap(
    cache_dir: Path,
    cache_key: Any,
    *,
    dpr: float = 1.0,
) -> QPixmap | None:
    try:
        cache_path = persistent_pixmap_cache_path(cache_dir, cache_key)
        if not cache_path.is_file():
            return None
        pixmap = QPixmap(str(cache_path))
    except OSError:
        return None
    pixmap.setDevicePixelRatio(effective_pixmap_dpr(dpr))
    return pixmap if not pixmap.isNull() else None


def save_persistent_pixmap(
    cache_dir: Path,
    cache_key: Any,
    pixmap: QPixmap,
) -> bool:
    if pixmap.isNull():
        return False
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_path = persistent_pixmap_cache_path(cache_dir, cache_key)
        return bool(pixmap.save(str(cache_path), "PNG"))
    except OSError:
        return False
