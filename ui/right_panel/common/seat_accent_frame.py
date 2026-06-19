from __future__ import annotations

from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QFrame, QWidget

from ui.utils.pvp_colors import pvp_player_color


class PvpSeatAccentFrame(QFrame):
    """Seat container whose accent is painted inside, without changing layout."""

    def __init__(
        self,
        seat: str,
        parent: QWidget | None = None,
        *,
        object_name: str = "",
    ) -> None:
        super().__init__(parent)
        self.seat = seat
        if object_name:
            self.setObjectName(object_name)
        self.setProperty("seat", seat)

    def refresh_player_color(self) -> None:
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().paintEvent(event)
        if self.width() < 4 or self.height() < 4:
            return
        color = QColor(pvp_player_color(self.seat))
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setPen(QPen(color, 3))
            painter.drawLine(2, 7, 2, max(7, self.height() - 8))
        finally:
            painter.end()


__all__ = ["PvpSeatAccentFrame"]
