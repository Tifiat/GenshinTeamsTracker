from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QScrollArea


def horizontal_wheel_delta(event, *, step: int = 40) -> int:
    pixel_delta = event.pixelDelta()
    if not pixel_delta.isNull():
        return -pixel_delta.y() if pixel_delta.y() else pixel_delta.x()

    angle_delta = event.angleDelta()
    raw_delta = -angle_delta.y() if angle_delta.y() else angle_delta.x()
    if not raw_delta:
        return 0
    return int(raw_delta / 120 * step)


class HorizontalDragScrollArea(QScrollArea):
    clicked = Signal()

    def __init__(self, parent=None, *, wheel_step: int = 40):
        super().__init__(parent)
        self._wheel_step = int(wheel_step)
        self._dragging = False
        self._drag_moved = False
        self._drag_start_x = 0
        self._drag_start_value = 0

    def wheelEvent(self, event) -> None:
        delta = horizontal_wheel_delta(event, step=self._wheel_step)
        if delta:
            bar = self.horizontalScrollBar()
            bar.setValue(bar.value() + delta)
            event.accept()
            return
        super().wheelEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._drag_moved = False
            self._drag_start_x = int(event.globalPosition().x())
            self._drag_start_value = self.horizontalScrollBar().value()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._dragging:
            delta = self._drag_start_x - int(event.globalPosition().x())
            if abs(delta) > 3:
                self._drag_moved = True
            self.horizontalScrollBar().setValue(self._drag_start_value + delta)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self._dragging and event.button() == Qt.MouseButton.LeftButton:
            should_click = not self._drag_moved
            self._dragging = False
            event.accept()
            if should_click:
                self.clicked.emit()
            return
        super().mouseReleaseEvent(event)
