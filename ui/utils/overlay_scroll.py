from __future__ import annotations

from PySide6.QtCore import QObject, QEvent, QPoint, QRect, Qt, QTimer
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QAbstractScrollArea, QScrollArea, QWidget


class OverlayVerticalScrollbar(QObject):
    """Auto-hidden vertical scrollbar painted over any QAbstractScrollArea."""

    def __init__(
        self,
        scroll_area: QAbstractScrollArea,
        *,
        auto_hide_ms: int = 900,
        edge_hover_width: int = 18,
        right_offset: int = 6,
    ) -> None:
        super().__init__(scroll_area)
        self._scroll_area = scroll_area
        self._auto_hide_ms = int(auto_hide_ms)
        self._edge_hover_width = int(edge_hover_width)
        self._right_offset = max(0, int(right_offset))
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._hide_overlay_if_idle)
        self._overlay = _OverlayVerticalScrollThumb(self)

        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.verticalScrollBar().rangeChanged.connect(self._sync_overlay)
        scroll_area.verticalScrollBar().valueChanged.connect(self._reveal_temporarily)
        scroll_area.viewport().installEventFilter(self)
        scroll_area.viewport().setMouseTracking(True)
        self._sync_overlay()

    @property
    def scroll_area(self) -> QAbstractScrollArea:
        return self._scroll_area

    @property
    def auto_hide_ms(self) -> int:
        return self._auto_hide_ms

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 - Qt override
        try:
            viewport = self._scroll_area.viewport()
        except RuntimeError:
            return False

        if obj is viewport:
            if event.type() == QEvent.Type.Resize:
                self._sync_overlay()
            elif event.type() == QEvent.Type.Wheel:
                self._reveal_temporarily()
            elif event.type() == QEvent.Type.Leave:
                self._hide_timer.start(self._auto_hide_ms)
            elif event.type() == QEvent.Type.MouseMove:
                pos = event.position().toPoint()
                if pos.x() >= viewport.width() - self._edge_hover_width:
                    self._show_overlay()
                elif not self._overlay.is_dragging:
                    self._hide_timer.start(self._auto_hide_ms)
        return super().eventFilter(obj, event)

    def _reveal_temporarily(self) -> None:
        self._show_overlay()
        if not self._overlay.is_dragging:
            self._hide_timer.start(self._auto_hide_ms)

    def _show_overlay(self) -> None:
        if not self._has_vertical_range():
            self._overlay.hide()
            return
        self._sync_overlay()
        self._hide_timer.stop()
        self._overlay.show()
        self._overlay.raise_()

    def _hide_overlay_if_idle(self) -> None:
        if not self._overlay.is_dragging:
            self._overlay.hide()

    def _has_vertical_range(self) -> bool:
        try:
            bar = self._scroll_area.verticalScrollBar()
        except RuntimeError:
            return False
        return bar.maximum() > bar.minimum()

    def _sync_overlay(self) -> None:
        try:
            viewport = self._scroll_area.viewport()
        except RuntimeError:
            return
        if viewport is None:
            return
        width = 8
        margin = 4
        viewport_geometry = viewport.geometry()
        base_x = (
            viewport_geometry.x()
            + viewport_geometry.width()
            - width
            - margin
            + self._right_offset
        )
        max_x = max(viewport_geometry.x(), self._scroll_area.width() - width)
        self._overlay.setGeometry(
            min(base_x, max_x),
            viewport_geometry.y() + margin,
            width,
            max(1, viewport_geometry.height() - margin * 2),
        )
        self._overlay.update()
        if not self._has_vertical_range():
            self._overlay.hide()


def install_overlay_vertical_scrollbar(
    scroll_area: QAbstractScrollArea,
    *,
    auto_hide_ms: int = 900,
    edge_hover_width: int = 18,
    right_offset: int = 6,
) -> OverlayVerticalScrollbar:
    return OverlayVerticalScrollbar(
        scroll_area,
        auto_hide_ms=auto_hide_ms,
        edge_hover_width=edge_hover_width,
        right_offset=right_offset,
    )


class OverlayVerticalScrollArea(QScrollArea):
    """QScrollArea with an auto-hidden vertical scrollbar painted over content."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        auto_hide_ms: int = 900,
        edge_hover_width: int = 18,
        right_offset: int = 6,
    ) -> None:
        super().__init__(parent)
        self._overlay_scrollbar = install_overlay_vertical_scrollbar(
            self,
            auto_hide_ms=auto_hide_ms,
            edge_hover_width=edge_hover_width,
            right_offset=right_offset,
        )

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().resizeEvent(event)
        self._overlay_scrollbar._sync_overlay()


class _OverlayVerticalScrollThumb(QWidget):
    def __init__(self, owner: OverlayVerticalScrollbar) -> None:
        super().__init__(owner.scroll_area)
        self._owner = owner
        self._dragging = False
        self._drag_start_y = 0
        self._drag_start_value = 0
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.hide()

    @property
    def is_dragging(self) -> bool:
        return self._dragging

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        del event
        thumb = self._thumb_rect()
        if thumb.isNull():
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(215, 180, 97, 72))
        painter.drawRoundedRect(self.rect(), 4, 4)
        painter.setBrush(QColor(215, 180, 97, 190 if self._dragging else 145))
        painter.drawRoundedRect(thumb, 4, 4)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        bar = self._owner.scroll_area.verticalScrollBar()
        thumb = self._thumb_rect()
        y = int(event.position().y())
        if not thumb.contains(QPoint(int(event.position().x()), y)):
            self._jump_to_y(y)
        self._dragging = True
        self._drag_start_y = y
        self._drag_start_value = bar.value()
        event.accept()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt override
        if not self._dragging:
            super().mouseMoveEvent(event)
            return
        bar = self._owner.scroll_area.verticalScrollBar()
        track = self.height()
        thumb = self._thumb_rect()
        travel = max(1, track - thumb.height())
        value_range = max(1, bar.maximum() - bar.minimum())
        delta_y = int(event.position().y()) - self._drag_start_y
        bar.setValue(
            self._drag_start_value + int(delta_y / travel * value_range)
        )
        event.accept()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt override
        if self._dragging and event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            self._owner._hide_timer.start(self._owner.auto_hide_ms)
            self.update()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def enterEvent(self, event) -> None:  # noqa: N802 - Qt override
        self._owner._show_overlay()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 - Qt override
        if not self._dragging:
            self._owner._hide_timer.start(self._owner.auto_hide_ms)
        super().leaveEvent(event)

    def _jump_to_y(self, y: int) -> None:
        bar = self._owner.scroll_area.verticalScrollBar()
        thumb = self._thumb_rect()
        track = self.height()
        travel = max(1, track - thumb.height())
        value_range = max(1, bar.maximum() - bar.minimum())
        centered = max(0, min(travel, y - thumb.height() // 2))
        bar.setValue(bar.minimum() + int(centered / travel * value_range))

    def _thumb_rect(self) -> QRect:
        bar = self._owner.scroll_area.verticalScrollBar()
        total = bar.maximum() - bar.minimum() + bar.pageStep()
        if total <= 0 or bar.maximum() <= bar.minimum():
            return QRect()
        track_height = self.height()
        thumb_height = max(32, int(track_height * bar.pageStep() / total))
        thumb_height = min(track_height, thumb_height)
        travel = max(1, track_height - thumb_height)
        value_range = max(1, bar.maximum() - bar.minimum())
        y = int((bar.value() - bar.minimum()) / value_range * travel)
        return QRect(0, y, self.width(), thumb_height)
