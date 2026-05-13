from __future__ import annotations

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtWidgets import (
    QPushButton,
    QSizePolicy,
    QStyle,
    QStyleOptionButton,
    QStylePainter,
)


class MarqueeButton(QPushButton):
    """QPushButton with scrolling text for overflow labels."""

    def __init__(self, text: str = "", parent=None):
        super().__init__(parent)

        self._offset = 0
        self._hovered = False
        self._gap = 28
        self._step = 1
        self._timer = QTimer(self)
        self._timer.setInterval(35)
        self._timer.timeout.connect(self._tick)

        self.setMouseTracking(True)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self.setText(text)

    def setText(self, text: str) -> None:
        super().setText(text)
        if hasattr(self, "_timer"):
            self._reset_scroll()

    def enterEvent(self, event) -> None:
        self._hovered = True
        self._sync_timer()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hovered = False
        self._reset_scroll()
        super().leaveEvent(event)

    def focusInEvent(self, event) -> None:
        self._sync_timer()
        super().focusInEvent(event)

    def focusOutEvent(self, event) -> None:
        self._reset_scroll()
        super().focusOutEvent(event)

    def resizeEvent(self, event) -> None:
        self._reset_scroll()
        super().resizeEvent(event)

    def checkStateSet(self) -> None:
        super().checkStateSet()
        self._sync_timer()

    def sizeHint(self) -> QSize:
        return QSize(0, super().sizeHint().height())

    def minimumSizeHint(self) -> QSize:
        return QSize(0, super().minimumSizeHint().height())

    def paintEvent(self, event) -> None:
        painter = QStylePainter(self)
        option = QStyleOptionButton()
        self.initStyleOption(option)

        text = option.text
        option.text = ""
        painter.drawControl(QStyle.ControlElement.CE_PushButton, option)

        text_rect = self.style().subElementRect(
            QStyle.SubElement.SE_PushButtonContents,
            option,
            self,
        )
        text_rect.adjust(4, 0, -4, 0)

        metrics = painter.fontMetrics()
        text_width = metrics.horizontalAdvance(text)
        painter.setClipRect(text_rect)
        painter.setPen(option.palette.buttonText().color())

        if not text:
            self._sync_timer(text_width, text_rect.width())
            return

        if text_width <= text_rect.width():
            painter.drawText(
                text_rect,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                text,
            )
            self._sync_timer(text_width, text_rect.width())
            return

        if not self._is_active():
            painter.drawText(
                text_rect,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                metrics.elidedText(
                    text,
                    Qt.TextElideMode.ElideRight,
                    text_rect.width(),
                ),
            )
            self._sync_timer(text_width, text_rect.width())
            return

        y = (
            text_rect.y()
            + (text_rect.height() + metrics.ascent() - metrics.descent()) // 2
        )
        first_x = text_rect.x() - self._offset
        painter.drawText(first_x, y, text)

        second_x = first_x + text_width + self._gap
        if second_x < text_rect.right():
            painter.drawText(second_x, y, text)

        self._sync_timer(text_width, text_rect.width())

    def _tick(self) -> None:
        text_width = self.fontMetrics().horizontalAdvance(self.text())
        if text_width <= self._available_text_width():
            self._reset_scroll()
            return

        self._offset += self._step
        cycle = text_width + self._gap
        if self._offset >= cycle:
            self._offset = 0
        self.update()

    def _reset_scroll(self) -> None:
        self._offset = 0
        self._sync_timer()
        self.update()

    def _is_active(self) -> bool:
        return self._hovered or self.hasFocus() or self.isChecked()

    def _available_text_width(self) -> int:
        option = QStyleOptionButton()
        self.initStyleOption(option)
        text_rect = self.style().subElementRect(
            QStyle.SubElement.SE_PushButtonContents,
            option,
            self,
        )
        text_rect.adjust(4, 0, -4, 0)
        return max(0, text_rect.width())

    def _sync_timer(
        self,
        text_width: int | None = None,
        available_width: int | None = None,
    ) -> None:
        text_width = (
            self.fontMetrics().horizontalAdvance(self.text())
            if text_width is None
            else text_width
        )
        available_width = (
            self._available_text_width()
            if available_width is None
            else available_width
        )

        should_run = self._is_active() and text_width > available_width

        if should_run and not self._timer.isActive():
            self._timer.start()
        elif not should_run and self._timer.isActive():
            self._timer.stop()
