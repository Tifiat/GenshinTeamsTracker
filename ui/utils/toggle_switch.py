from __future__ import annotations

from PySide6.QtCore import Property, QEasingCurve, QPropertyAnimation, QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QAbstractButton, QSizePolicy, QWidget

from ui.utils.ui_palette import (
    UI_BG_BUTTON,
    UI_BG_BUTTON_CHECKED,
    UI_BG_BUTTON_HOVER,
    UI_BG_PANEL,
    UI_BORDER_FILTER_SELECTED,
    UI_BORDER_DEFAULT,
    UI_STATE_DANGER,
    UI_STATE_SUCCESS,
    UI_TEXT_ON_ACCENT,
    UI_TEXT_PRIMARY,
    UI_TEXT_SECONDARY,
)


TOGGLE_SWITCH_WIDTH = 46
TOGGLE_SWITCH_HEIGHT = 24
TOGGLE_SWITCH_PADDING = 3
TOGGLE_SWITCH_ANIMATION_MS = 120
FILTER_MODE_TOGGLE_WIDTH = 78
FILTER_MODE_TOGGLE_HEIGHT = 34
SORT_ICON_BUTTON_SIZE = 40
FILTER_ACTION_BUTTON_HEIGHT = 34
FILTER_ACTION_BUTTON_MIN_WIDTH = 188


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


class FilterModeToggle(QAbstractButton):
    """Two-state vector filter toggle for include/exclude-style filters."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt override
        return QSize(FILTER_MODE_TOGGLE_WIDTH, FILTER_MODE_TOGGLE_HEIGHT)

    def minimumSizeHint(self) -> QSize:  # noqa: N802 - Qt override
        return self.sizeHint()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        _draw_filter_mode_toggle(
            painter,
            QRectF(self.rect()).adjusted(1, 1, -1, -1),
            checked=self.isChecked(),
            hovered=self.underMouse(),
            enabled=self.isEnabled(),
        )


class SortIconButton(QAbstractButton):
    """Compact vector sort button with an optional count badge."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setCheckable(False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._count = 0

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt override
        return QSize(SORT_ICON_BUTTON_SIZE, SORT_ICON_BUTTON_SIZE)

    def minimumSizeHint(self) -> QSize:  # noqa: N802 - Qt override
        return self.sizeHint()

    def count(self) -> int:
        return self._count

    def setCount(self, count: int) -> None:  # noqa: N802 - Qt-style setter
        self._count = max(0, int(count))
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        checked = self._count > 0
        fill = QColor(UI_BG_BUTTON_CHECKED if checked else UI_BG_BUTTON)
        if self.underMouse():
            fill = QColor(UI_BG_BUTTON_HOVER)
        border = QColor(UI_BORDER_FILTER_SELECTED if checked else UI_BORDER_DEFAULT)
        border.setAlpha(220 if self.underMouse() else 170)
        painter.setPen(QPen(border, 1.2))
        painter.setBrush(fill)
        painter.drawEllipse(rect)

        icon_color = QColor(UI_TEXT_ON_ACCENT if checked else UI_TEXT_SECONDARY)
        _draw_sort_icon(painter, rect.adjusted(10, 9, -9, -9), icon_color)
        if self._count:
            _draw_count_badge(painter, rect, str(self._count))


class FilterActionButton(QWidget):
    """Unified action button with a left embedded filter toggle zone."""

    actionPressed = Signal()
    actionClicked = Signal()
    filterToggled = Signal(bool)

    def __init__(self, text: str = "", parent=None) -> None:
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._text = text
        self._filter_checked = False
        self._hover_zone = ""
        self._pressed_zone = ""

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt override
        return QSize(FILTER_ACTION_BUTTON_MIN_WIDTH, FILTER_ACTION_BUTTON_HEIGHT)

    def minimumSizeHint(self) -> QSize:  # noqa: N802 - Qt override
        return self.sizeHint()

    def text(self) -> str:
        return self._text

    def setText(self, text: str) -> None:  # noqa: N802 - Qt-style setter
        self._text = str(text)
        self.update()

    def isFilterChecked(self) -> bool:  # noqa: N802 - Qt-style getter
        return self._filter_checked

    def setFilterChecked(self, checked: bool, *, notify: bool = False) -> None:  # noqa: N802
        checked = bool(checked)
        if self._filter_checked == checked:
            return
        self._filter_checked = checked
        self.update()
        if notify:
            self.filterToggled.emit(checked)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        radius = rect.height() / 2
        border = QColor(UI_BORDER_DEFAULT)
        if self._hover_zone == "action":
            border = QColor(UI_BORDER_FILTER_SELECTED)
            border.setAlpha(180)
        painter.setPen(QPen(border, 1.2))
        painter.setBrush(QColor(UI_BG_BUTTON_HOVER if self._hover_zone == "action" else UI_BG_BUTTON))
        painter.drawRoundedRect(rect, radius, radius)

        toggle_rect = self._toggle_rect()
        _draw_filter_mode_toggle(
            painter,
            toggle_rect,
            checked=self._filter_checked,
            hovered=self._hover_zone == "filter",
            enabled=self.isEnabled(),
        )

        text_rect = rect.adjusted(toggle_rect.width() + 7, 0, -10, 0)
        painter.setPen(QColor(UI_TEXT_PRIMARY))
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, self._text)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt override
        zone = self._zone_at(event.position())
        if self._hover_zone != zone:
            self._hover_zone = zone
            self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 - Qt override
        self._hover_zone = ""
        self._pressed_zone = ""
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        self._pressed_zone = self._zone_at(event.position())
        if self._pressed_zone == "action":
            self.actionPressed.emit()
        event.accept()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.button() != Qt.MouseButton.LeftButton:
            super().mouseReleaseEvent(event)
            return
        zone = self._zone_at(event.position())
        pressed_zone = self._pressed_zone
        self._pressed_zone = ""
        if zone == "filter" and pressed_zone == "filter":
            self.setFilterChecked(not self._filter_checked, notify=True)
            event.accept()
            return
        if zone == "action" and pressed_zone == "action":
            self.actionClicked.emit()
            event.accept()
            return
        event.accept()

    def _toggle_rect(self) -> QRectF:
        outer = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        height = min(FILTER_MODE_TOGGLE_HEIGHT, outer.height())
        width = min(FILTER_MODE_TOGGLE_WIDTH, outer.width() - 2)
        return QRectF(
            outer.left(),
            outer.top() + (outer.height() - height) / 2,
            width,
            height,
        ).adjusted(0, 0, -1, 0)

    def _zone_at(self, position) -> str:
        point = QPointF(position)
        if self._toggle_rect().contains(point):
            return "filter"
        if QRectF(self.rect()).contains(point):
            return "action"
        return ""


def _draw_filter_mode_toggle(
    painter: QPainter,
    rect: QRectF,
    *,
    checked: bool,
    hovered: bool,
    enabled: bool,
) -> None:
    radius = rect.height() / 2
    border = QColor(UI_BORDER_FILTER_SELECTED if not checked else UI_BORDER_DEFAULT)
    border.setAlpha(210 if hovered else 165)
    fill = QColor(UI_BG_BUTTON_HOVER if hovered else UI_BG_BUTTON)
    if not enabled:
        fill.setAlpha(95)
        border.setAlpha(95)
    painter.setPen(QPen(border, 1.2))
    painter.setBrush(fill)
    painter.drawRoundedRect(rect, radius, radius)

    half_width = rect.width() / 2
    active_rect = QRectF(
        rect.left() if not checked else rect.left() + half_width,
        rect.top() + 3,
        half_width,
        rect.height() - 6,
    ).adjusted(2, 0, -2, 0)
    active_color = QColor(UI_STATE_SUCCESS if not checked else UI_BG_BUTTON_CHECKED)
    active_color.setAlpha(185 if not checked else 170)
    if not enabled:
        active_color.setAlpha(85)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(active_color)
    painter.drawRoundedRect(active_rect, active_rect.height() / 2, active_rect.height() / 2)

    left_rect = QRectF(rect.left() + 9, rect.top() + 7, 20, 20)
    right_rect = QRectF(rect.left() + half_width + 9, rect.top() + 7, 20, 20)
    inactive_icon = QColor(UI_TEXT_SECONDARY)
    inactive_icon.setAlpha(145 if enabled else 80)
    active_icon = QColor(UI_TEXT_ON_ACCENT)
    if not enabled:
        active_icon.setAlpha(140)

    _draw_filter_icon(painter, left_rect, active_icon if not checked else inactive_icon)
    _draw_filter_icon(painter, right_rect, inactive_icon)
    _draw_ban_badge(painter, right_rect.adjusted(11, 11, 5, 5))


def _draw_filter_icon(painter: QPainter, rect: QRectF, color: QColor) -> None:
    path = QPainterPath()
    path.moveTo(rect.left() + rect.width() * 0.14, rect.top() + rect.height() * 0.18)
    path.lineTo(rect.right() - rect.width() * 0.14, rect.top() + rect.height() * 0.18)
    path.lineTo(rect.left() + rect.width() * 0.58, rect.top() + rect.height() * 0.53)
    path.lineTo(rect.left() + rect.width() * 0.58, rect.bottom() - rect.height() * 0.16)
    path.lineTo(rect.left() + rect.width() * 0.42, rect.bottom() - rect.height() * 0.07)
    path.lineTo(rect.left() + rect.width() * 0.42, rect.top() + rect.height() * 0.53)
    path.closeSubpath()
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(color)
    painter.drawPath(path)

    stem_color = QColor(color)
    stem_color.setAlpha(max(80, stem_color.alpha() - 35))
    painter.setPen(QPen(stem_color, 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    y = rect.bottom() - rect.height() * 0.18
    painter.drawLine(rect.left() + rect.width() * 0.68, y, rect.right() - rect.width() * 0.08, y)


def _draw_ban_badge(painter: QPainter, rect: QRectF) -> None:
    color = QColor(UI_STATE_DANGER)
    color.setAlpha(235)
    painter.setPen(QPen(color, 1.7))
    painter.setBrush(QColor(UI_BG_PANEL))
    painter.drawEllipse(rect)
    painter.drawLine(
        rect.left() + rect.width() * 0.28,
        rect.bottom() - rect.height() * 0.28,
        rect.right() - rect.width() * 0.28,
        rect.top() + rect.height() * 0.28,
    )


def _draw_sort_icon(painter: QPainter, rect: QRectF, color: QColor) -> None:
    painter.setPen(QPen(color, 2.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    x_left = rect.left() + rect.width() * 0.18
    x_right = rect.right() - rect.width() * 0.08
    ys = (
        rect.top() + rect.height() * 0.20,
        rect.top() + rect.height() * 0.50,
        rect.top() + rect.height() * 0.80,
    )
    for index, y in enumerate(ys):
        start = x_left + index * rect.width() * 0.10
        painter.drawLine(start, y, x_right, y)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(color)
    for y in ys:
        painter.drawEllipse(QRectF(rect.left(), y - 2.1, 4.2, 4.2))


def _draw_count_badge(painter: QPainter, rect: QRectF, text: str) -> None:
    badge_size = 16
    badge_rect = QRectF(
        rect.right() - badge_size + 1,
        rect.bottom() - badge_size + 1,
        badge_size,
        badge_size,
    )
    fill = QColor(UI_STATE_SUCCESS)
    fill.setAlpha(225)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(fill)
    painter.drawEllipse(badge_rect)
    painter.setPen(QColor(UI_TEXT_ON_ACCENT))
    font = painter.font()
    font.setPointSize(max(7, font.pointSize() - 2))
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, text[:2])
