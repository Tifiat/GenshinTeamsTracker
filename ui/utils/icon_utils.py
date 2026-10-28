from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap

from hoyolab_export.paths import PROJECT_ROOT


UI_ICON_DIR = PROJECT_ROOT / "assets" / "ui" / "icons"

DEFAULT_LIGHT_ICON = "#dce5f7"
DEFAULT_DARK_ICON = "#17191f"


def _relative_luminance(color: QColor) -> float:
    def channel(value: int) -> float:
        c = value / 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r = channel(color.red())
    g = channel(color.green())
    b = channel(color.blue())
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_icon_color(
    background: str | QColor,
    *,
    light: str = DEFAULT_LIGHT_ICON,
    dark: str = DEFAULT_DARK_ICON,
) -> str:
    bg = _normalize_qcolor(background)
    return dark if _relative_luminance(bg) > 0.45 else light


def _normalize_qcolor(color: str | QColor) -> QColor:
    return QColor(color) if not isinstance(color, QColor) else QColor(color)


def _color_key(color: str | QColor) -> str:
    normalized = _normalize_qcolor(color)
    return normalized.name(QColor.NameFormat.HexArgb)


@lru_cache(maxsize=512)
def _tinted_svg_pixmap_cached(icon_name: str, size: int, color_key: str) -> QPixmap:
    source = QIcon(str(UI_ICON_DIR / f"{icon_name}.svg")).pixmap(size, size)

    result = QPixmap(source.size())
    result.setDevicePixelRatio(source.devicePixelRatio())
    result.fill(Qt.GlobalColor.transparent)

    painter = QPainter(result)
    painter.drawPixmap(0, 0, source)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    painter.fillRect(result.rect(), QColor(color_key))
    painter.end()

    return result


@lru_cache(maxsize=512)
def _tinted_svg_icon_cached(icon_name: str, size: int, color_key: str) -> QIcon:
    return QIcon(_tinted_svg_pixmap_cached(icon_name, size, color_key))


def tinted_svg_pixmap(icon_name: str, size: int, color: str | QColor) -> QPixmap:
    return _tinted_svg_pixmap_cached(icon_name, size, _color_key(color))


def tinted_svg_icon(icon_name: str, size: int, color: str | QColor) -> QIcon:
    return _tinted_svg_icon_cached(icon_name, size, _color_key(color))


def auto_contrast_svg_pixmap(
    icon_name: str,
    size: int,
    background: str | QColor,
) -> QPixmap:
    return tinted_svg_pixmap(
        icon_name,
        size,
        contrast_icon_color(background),
    )


def auto_contrast_svg_icon(
    icon_name: str,
    size: int,
    background: str | QColor,
) -> QIcon:
    return tinted_svg_icon(
        icon_name,
        size,
        contrast_icon_color(background),
    )
