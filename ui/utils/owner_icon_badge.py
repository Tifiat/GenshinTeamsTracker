from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap


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