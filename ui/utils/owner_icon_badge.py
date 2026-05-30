from __future__ import annotations

from PySide6.QtCore import QRect, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap


DEFAULT_OWNER_BADGE_SIZE_RATIO = 43 / 70
DEFAULT_OWNER_BADGE_OFFSET_X_RATIO = 1 / 70
DEFAULT_OWNER_BADGE_OFFSET_Y_RATIO = 16 / 70


def owner_badge_size_for_icon(
    icon_size: QSize,
    *,
    size_ratio: float = DEFAULT_OWNER_BADGE_SIZE_RATIO,
) -> QSize:
    return QSize(
        max(1, round(icon_size.width() * size_ratio)),
        max(1, round(icon_size.height() * size_ratio)),
    )


def owner_badge_rect_for_icon_rect(
    icon_rect: QRect,
    badge_size: QSize,
    *,
    offset_x_ratio: float = DEFAULT_OWNER_BADGE_OFFSET_X_RATIO,
    offset_y_ratio: float = DEFAULT_OWNER_BADGE_OFFSET_Y_RATIO,
) -> QRect:
    return QRect(
        icon_rect.center().x() - badge_size.width() // 2 + round(icon_rect.width() * offset_x_ratio),
        icon_rect.center().y() - badge_size.height() // 2 + round(icon_rect.height() * offset_y_ratio),
        badge_size.width(),
        badge_size.height(),
    )


def make_owner_icon_badge_background(
    size: QSize,
    *,
    fill_color: str = "#6f7684",
    fill_alpha: int = 150,
    border_color: str = "#ffffff",
    border_alpha: int = 210,
    border_width: float = 2.0,
    inset: float = 1.0,
) -> QPixmap:
    """Return a transparent pixmap with a simple circular owner badge background.

    This intentionally draws only a semi-transparent gray circle and a white
    outline. Character side icons are composed by callers so each UI surface can
    tune icon size and placement independently.
    """
    width = max(1, int(size.width()))
    height = max(1, int(size.height()))
    diameter = min(width, height)

    pixmap = QPixmap(width, height)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    x = (width - diameter) / 2 + inset
    y = (height - diameter) / 2 + inset
    circle_size = max(1.0, diameter - inset * 2)
    circle_rect = QRectF(x, y, circle_size, circle_size)

    fill = QColor(fill_color)
    fill.setAlpha(max(0, min(255, int(fill_alpha))))
    border = QColor(border_color)
    border.setAlpha(max(0, min(255, int(border_alpha))))

    painter.setBrush(fill)
    painter.setPen(QPen(border, border_width))
    painter.drawEllipse(circle_rect)

    painter.end()
    return pixmap