from __future__ import annotations

from PySide6.QtCore import Property, QEasingCurve, QPropertyAnimation, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QAbstractButton, QSizePolicy

from ui.utils.ui_palette import (
    UI_BG_BUTTON,
    UI_BG_BUTTON_CHECKED,
    UI_BG_BUTTON_HOVER,
    UI_BORDER_DEFAULT,
    UI_STATE_SUCCESS,
    UI_TEXT_ON_ACCENT,
)


TOGGLE_SWITCH_WIDTH = 46
TOGGLE_SWITCH_HEIGHT = 24
TOGGLE_SWITCH_PADDING = 3
TOGGLE_SWITCH_ANIMATION_MS = 120


class ToggleSwitch(QAbstractButton):
    """Reusable vector on/off switch drawn with Qt painting primitives."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._position = 1.0 if self.isChecked() else 0.0
        self._animation = QPropertyAnimation(self, b"position", self)
        self._animation.setDuration(TOGGLE_SWITCH_ANIMATION_MS)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.toggled.connect(self._animate_to_state)

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt override
        return QSize(TOGGLE_SWITCH_WIDTH, TOGGLE_SWITCH_HEIGHT)

    def minimumSizeHint(self) -> QSize:  # noqa: N802 - Qt override
        return self.sizeHint()

    def position(self) -> float:
        return self._position

    def setPosition(self, value: float) -> None:  # noqa: N802 - Qt property setter
        self._position = max(0.0, min(1.0, float(value)))
        self.update()

    position = Property(float, position, setPosition)

    def setChecked(self, checked: bool) -> None:  # noqa: N802 - Qt override
        super().setChecked(checked)
        if not self.isVisible():
            self._animation.stop()
            self._position = 1.0 if checked else 0.0
            self.update()

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Down):
            self.setChecked(False)
            event.accept()
            return
        if event.key() in (Qt.Key.Key_Right, Qt.Key.Key_Up):
            self.setChecked(True)
            event.accept()
            return
        super().keyPressEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        radius = rect.height() / 2
        track_color = self._track_color()
        border_color = QColor(UI_STATE_SUCCESS if self.isChecked() else UI_BORDER_DEFAULT)
        if not self.isEnabled():
            track_color.setAlpha(95)
            border_color.setAlpha(95)

        painter.setPen(QPen(border_color, 1.2))
        painter.setBrush(track_color)
        painter.drawRoundedRect(rect, radius, radius)

        knob_size = max(1.0, rect.height() - TOGGLE_SWITCH_PADDING * 2)
        x_min = rect.left() + TOGGLE_SWITCH_PADDING
        x_max = rect.right() - TOGGLE_SWITCH_PADDING - knob_size
        knob_x = x_min + (x_max - x_min) * self._position
        knob_rect = QRectF(
            knob_x,
            rect.top() + TOGGLE_SWITCH_PADDING,
            knob_size,
            knob_size,
        )
        knob_color = QColor(UI_TEXT_ON_ACCENT)
        if not self.isEnabled():
            knob_color.setAlpha(150)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(knob_color)
        painter.drawEllipse(knob_rect)

    def _track_color(self) -> QColor:
        if self.isChecked():
            color = QColor(UI_STATE_SUCCESS)
            color.setAlpha(185 if self.underMouse() else 165)
            return color
        if self.underMouse():
            return QColor(UI_BG_BUTTON_HOVER)
        return QColor(UI_BG_BUTTON)

    def _animate_to_state(self, checked: bool) -> None:
        self._animation.stop()
        self._animation.setStartValue(self._position)
        self._animation.setEndValue(1.0 if checked else 0.0)
        self._animation.start()
