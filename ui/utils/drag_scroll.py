from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QColor, QLinearGradient, QPainter
from PySide6.QtWidgets import QScrollArea, QWidget

from ui.utils.icon_utils import tinted_svg_pixmap


class DragScrollArea(QScrollArea):
    clicked = Signal()

    def __init__(
        self,
        parent=None,
        *,
        orientation: Qt.Orientation = Qt.Orientation.Horizontal,
        wheel_step: int = 40,
        edge_hint_size: int = 32,
        edge_icon_size: int = 20,
        edge_icon_color: str = "#dce5f7",
        edge_background: str = "#000000",
    ) -> None:
        super().__init__(parent)
        self._orientation = orientation
        self._wheel_step = int(wheel_step)
        self._edge_hint_size = max(0, int(edge_hint_size))
        self._dragging = False
        self._drag_moved = False
        self._drag_start_pos = 0
        self._drag_start_value = 0

        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        if self._is_horizontal:
            start_icon = "chevron-left"
            end_icon = "chevron-right"
        else:
            start_icon = "chevron-up"
            end_icon = "chevron-down"

        self._start_hint = _EdgeHint(
            start_icon,
            "start",
            orientation=self._orientation,
            edge_icon_size=edge_icon_size,
            edge_icon_color=edge_icon_color,
            edge_background=edge_background,
            parent=self,
        )
        self._end_hint = _EdgeHint(
            end_icon,
            "end",
            orientation=self._orientation,
            edge_icon_size=edge_icon_size,
            edge_icon_color=edge_icon_color,
            edge_background=edge_background,
            parent=self,
        )
        self._start_hint.hide()
        self._end_hint.hide()

        self.viewport().installEventFilter(self)
        bar = self._scroll_bar()
        bar.valueChanged.connect(self.update_edge_hints)
        bar.rangeChanged.connect(lambda _min, _max: self.update_edge_hints())

    @property
    def _is_horizontal(self) -> bool:
        return self._orientation == Qt.Orientation.Horizontal

    def setWidget(self, widget: QWidget | None) -> None:  # noqa: N802 - Qt override
        old_widget = self.widget()
        if old_widget is not None:
            old_widget.removeEventFilter(self)

        super().setWidget(widget)

        if widget is not None:
            widget.installEventFilter(self)
        self.update_edge_hints()

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().resizeEvent(event)
        self._sync_hint_geometry()
        self.update_edge_hints()

    def wheelEvent(self, event) -> None:  # noqa: N802 - Qt override
        if self._scroll_by_wheel(event):
            event.accept()
            return
        super().wheelEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.button() == Qt.MouseButton.LeftButton:
            self._begin_drag(event)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt override
        if self._dragging:
            self._drag_to(event)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt override
        if self._dragging and event.button() == Qt.MouseButton.LeftButton:
            should_click = not self._drag_moved
            self._end_drag()
            event.accept()
            if should_click:
                self.clicked.emit()
            return
        super().mouseReleaseEvent(event)

    def eventFilter(self, watched, event) -> bool:  # noqa: N802 - Qt override
        event_type = event.type()

        if event_type == QEvent.Type.Wheel:
            if self._scroll_by_wheel(event):
                event.accept()
                return True
            return False

        if event_type == QEvent.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.LeftButton:
                self._begin_drag(event)
            return False

        if event_type == QEvent.Type.MouseMove and self._dragging:
            self._drag_to(event)
            if self._drag_moved:
                event.accept()
                return True
            return False

        if event_type == QEvent.Type.MouseButtonRelease and self._dragging:
            moved = self._drag_moved
            self._end_drag()
            if moved:
                event.accept()
                return True
            return False

        return super().eventFilter(watched, event)

    def update_edge_hints(self) -> None:
        bar = self._scroll_bar()
        can_scroll_start = bar.value() > bar.minimum()
        can_scroll_end = bar.value() < bar.maximum()

        self._start_hint.setVisible(can_scroll_start)
        self._end_hint.setVisible(can_scroll_end)

        if can_scroll_start:
            self._start_hint.raise_()
        if can_scroll_end:
            self._end_hint.raise_()

    def _scroll_bar(self):
        return self.horizontalScrollBar() if self._is_horizontal else self.verticalScrollBar()

    def _event_pos(self, event) -> int:
        pos = event.globalPosition()
        return int(pos.x()) if self._is_horizontal else int(pos.y())

    def _wheel_delta(self, event) -> int:
        pixel_delta = event.pixelDelta()
        if not pixel_delta.isNull():
            if self._is_horizontal:
                return -pixel_delta.y() if pixel_delta.y() else pixel_delta.x()
            return -pixel_delta.y() if pixel_delta.y() else -pixel_delta.x()

        angle_delta = event.angleDelta()
        if self._is_horizontal:
            raw_delta = -angle_delta.y() if angle_delta.y() else angle_delta.x()
        else:
            raw_delta = -angle_delta.y() if angle_delta.y() else -angle_delta.x()
        if not raw_delta:
            return 0
        return int(raw_delta / 120 * self._wheel_step)

    def _scroll_by_wheel(self, event) -> bool:
        bar = self._scroll_bar()
        if bar.maximum() <= bar.minimum():
            return False

        delta = self._wheel_delta(event)
        if not delta:
            return False

        bar.setValue(bar.value() + delta)
        self.update_edge_hints()
        return True

    def _begin_drag(self, event) -> None:
        self._dragging = True
        self._drag_moved = False
        self._drag_start_pos = self._event_pos(event)
        self._drag_start_value = self._scroll_bar().value()

    def _drag_to(self, event) -> None:
        delta = self._drag_start_pos - self._event_pos(event)
        if abs(delta) > 3:
            self._drag_moved = True
        self._scroll_bar().setValue(self._drag_start_value + delta)
        self.update_edge_hints()

    def _end_drag(self) -> None:
        self._dragging = False
        self._drag_moved = False

    def _sync_hint_geometry(self) -> None:
        viewport = self.viewport()
        rect = viewport.geometry()
        size = self._edge_hint_size

        if self._is_horizontal:
            self._start_hint.setGeometry(rect.x(), rect.y(), size, rect.height())
            self._end_hint.setGeometry(
                rect.x() + max(0, rect.width() - size),
                rect.y(),
                size,
                rect.height(),
            )
        else:
            self._start_hint.setGeometry(rect.x(), rect.y(), rect.width(), size)
            self._end_hint.setGeometry(
                rect.x(),
                rect.y() + max(0, rect.height() - size),
                rect.width(),
                size,
            )


class HorizontalDragScrollArea(DragScrollArea):
    def __init__(self, parent=None, *, wheel_step: int = 40, **kwargs) -> None:
        super().__init__(
            parent,
            orientation=Qt.Orientation.Horizontal,
            wheel_step=wheel_step,
            **kwargs,
        )


class VerticalDragScrollArea(DragScrollArea):
    def __init__(self, parent=None, *, wheel_step: int = 40, **kwargs) -> None:
        super().__init__(
            parent,
            orientation=Qt.Orientation.Vertical,
            wheel_step=wheel_step,
            **kwargs,
        )


class _EdgeHint(QWidget):
    def __init__(
        self,
        icon_name: str,
        side: str,
        *,
        orientation: Qt.Orientation,
        edge_icon_size: int,
        edge_icon_color: str,
        edge_background: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._side = side
        self._orientation = orientation
        self._background = QColor(edge_background)
        self._icon = tinted_svg_pixmap(icon_name, int(edge_icon_size), edge_icon_color)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

    @property
    def _is_horizontal(self) -> bool:
        return self._orientation == Qt.Orientation.Horizontal

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        del event

        painter = QPainter(self)
        if self._is_horizontal:
            gradient = QLinearGradient(0, 0, self.width(), 0)
        else:
            gradient = QLinearGradient(0, 0, 0, self.height())

        edge_color = QColor(self._background)
        edge_color.setAlpha(255)
        clear_color = QColor(self._background)
        clear_color.setAlpha(0)

        if self._side == "start":
            gradient.setColorAt(0.0, edge_color)
            gradient.setColorAt(1.0, clear_color)
        else:
            gradient.setColorAt(0.0, clear_color)
            gradient.setColorAt(1.0, edge_color)

        painter.fillRect(self.rect(), gradient)

        ratio = self._icon.devicePixelRatio() or 1.0
        icon_width = self._icon.width() / ratio
        icon_height = self._icon.height() / ratio
        x = int((self.width() - icon_width) / 2)
        y = int((self.height() - icon_height) / 2)
        painter.drawPixmap(x, y, self._icon)