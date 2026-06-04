from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ui.utils.toggle_switch import ToggleSwitch  # noqa: E402
from ui.utils.ui_palette import (  # noqa: E402
    UI_BG_APP,
    UI_BG_BUTTON,
    UI_BG_BUTTON_CHECKED,
    UI_BG_BUTTON_HOVER,
    UI_BG_PANEL,
    UI_BORDER_FILTER_SELECTED,
    UI_BORDER_DEFAULT,
    UI_STATE_DANGER,
    UI_STATE_SUCCESS,
    UI_TEXT_MUTED,
    UI_TEXT_ON_ACCENT,
    UI_TEXT_PRIMARY,
    UI_TEXT_SECONDARY,
)


class FilterModeToggle(QAbstractButton):
    """Experiment-only two-state filter toggle with vector icons."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(78, 34)

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt override
        return QSize(78, 34)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        radius = rect.height() / 2

        border = QColor(UI_BORDER_FILTER_SELECTED if self.isChecked() else UI_BORDER_DEFAULT)
        border.setAlpha(210 if self.underMouse() else 165)
        painter.setPen(QPen(border, 1.2))
        painter.setBrush(QColor(UI_BG_BUTTON_HOVER if self.underMouse() else UI_BG_BUTTON))
        painter.drawRoundedRect(rect, radius, radius)

        half_width = rect.width() / 2
        active_rect = QRectF(
            rect.left() + (half_width if self.isChecked() else 0),
            rect.top() + 3,
            half_width,
            rect.height() - 6,
        ).adjusted(2, 0, -2, 0)
        active_color = QColor(UI_STATE_SUCCESS if self.isChecked() else UI_BG_BUTTON_CHECKED)
        active_color.setAlpha(130 if self.isChecked() else 185)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(active_color)
        painter.drawRoundedRect(active_rect, active_rect.height() / 2, active_rect.height() / 2)

        left_rect = QRectF(rect.left() + 9, rect.top() + 7, 20, 20)
        right_rect = QRectF(rect.left() + half_width + 9, rect.top() + 7, 20, 20)
        inactive_icon = QColor(UI_TEXT_SECONDARY)
        inactive_icon.setAlpha(155)
        active_icon = QColor(UI_TEXT_ON_ACCENT if self.isChecked() else UI_TEXT_SECONDARY)

        _draw_filter_icon(
            painter,
            left_rect,
            active_icon if not self.isChecked() else inactive_icon,
        )
        _draw_filter_icon(
            painter,
            right_rect,
            active_icon if self.isChecked() else inactive_icon,
        )
        _draw_ban_badge(painter, right_rect.adjusted(11, 11, 5, 5))


class SortCircleButton(QAbstractButton):
    """Experiment-only circular sort button with a vector list/sort glyph."""

    clicked_with_state = Signal(bool)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(40, 40)
        self.toggled.connect(self.clicked_with_state.emit)

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt override
        return QSize(40, 40)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        fill = QColor(UI_BG_BUTTON_CHECKED if self.isChecked() else UI_BG_BUTTON)
        if self.underMouse():
            fill = QColor(UI_BG_BUTTON_HOVER)
        border = QColor(UI_BORDER_FILTER_SELECTED if self.isChecked() else UI_BORDER_DEFAULT)
        border.setAlpha(220 if self.underMouse() else 170)
        painter.setPen(QPen(border, 1.2))
        painter.setBrush(fill)
        painter.drawEllipse(rect)

        icon_color = QColor(UI_TEXT_ON_ACCENT if self.isChecked() else UI_TEXT_SECONDARY)
        _draw_sort_icon(painter, rect.adjusted(10, 9, -9, -9), icon_color)


class SetsFilterButton(QWidget):
    """Experiment-only composite: embedded filter toggle + button body."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedHeight(40)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.filter_toggle = FilterModeToggle()
        self.status = QLabel("Filter: normal")
        self.status.setObjectName("Muted")
        self.body = _SetsButtonBody()

        layout.addWidget(self.filter_toggle)
        layout.addWidget(self.body, 1)
        layout.addWidget(self.status)

        self.filter_toggle.toggled.connect(self._on_filter_toggled)
        self.body.clicked.connect(self._on_body_clicked)

    def _on_filter_toggled(self, checked: bool) -> None:
        self.status.setText("Filter: exclude" if checked else "Filter: normal")

    def _on_body_clicked(self) -> None:
        self.status.setText("Sets button clicked")


class _SetsButtonBody(QAbstractButton):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumWidth(210)
        self.setFixedHeight(34)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        fill = QColor(UI_BG_BUTTON_HOVER if self.underMouse() else UI_BG_BUTTON)
        border = QColor(UI_BORDER_DEFAULT)
        painter.setPen(QPen(border, 1.1))
        painter.setBrush(fill)
        painter.drawRoundedRect(rect, rect.height() / 2, rect.height() / 2)
        painter.setPen(QColor(UI_TEXT_PRIMARY))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "Filter sets active")


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


def _row(label: str, switch: QAbstractButton, value_label: QLabel | None = None) -> QWidget:
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(10)
    text = QLabel(label)
    text.setFixedWidth(150)
    layout.addWidget(text)
    layout.addWidget(switch)
    if value_label is not None:
        layout.addWidget(value_label)
    layout.addStretch(1)
    return row


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyleSheet(
        f"""
        QWidget {{
            background: {UI_BG_APP};
            color: {UI_TEXT_PRIMARY};
            font-family: Segoe UI;
            font-size: 13px;
        }}
        QFrame#Panel {{
            background: {UI_BG_PANEL};
            border: 1px solid {UI_BORDER_DEFAULT};
            border-radius: 6px;
        }}
        QLabel#Muted {{
            color: {UI_TEXT_MUTED};
        }}
        """
    )

    window = QWidget()
    window.setWindowTitle("ToggleSwitch Probe")
    root = QVBoxLayout(window)
    root.setContentsMargins(16, 16, 16, 16)
    root.setSpacing(12)

    title = QLabel("ToggleSwitch probe")
    title.setStyleSheet("font-size: 18px; font-weight: 700;")
    root.addWidget(title)

    hint = QLabel("Click toggles, Space toggles, Left/Down = off, Right/Up = on.")
    hint.setObjectName("Muted")
    root.addWidget(hint)

    panel = QFrame()
    panel.setObjectName("Panel")
    panel_layout = QVBoxLayout(panel)
    panel_layout.setContentsMargins(14, 14, 14, 14)
    panel_layout.setSpacing(12)

    value_label = QLabel("off")
    interactive = ToggleSwitch()
    interactive.toggled.connect(lambda checked: value_label.setText("on" if checked else "off"))
    panel_layout.addWidget(_row("Interactive", interactive, value_label))

    checked = ToggleSwitch()
    checked.setChecked(True)
    panel_layout.addWidget(_row("Initially on", checked))

    disabled_off = ToggleSwitch()
    disabled_off.setEnabled(False)
    panel_layout.addWidget(_row("Disabled off", disabled_off))

    disabled_on = ToggleSwitch()
    disabled_on.setChecked(True)
    disabled_on.setEnabled(False)
    panel_layout.addWidget(_row("Disabled on", disabled_on))

    compact_row = QWidget()
    compact_layout = QHBoxLayout(compact_row)
    compact_layout.setContentsMargins(0, 0, 0, 0)
    compact_layout.setSpacing(8)
    compact_layout.addWidget(QLabel("Dense row"))
    for index in range(4):
        toggle = ToggleSwitch()
        toggle.setChecked(index % 2 == 0)
        compact_layout.addWidget(toggle, alignment=Qt.AlignmentFlag.AlignLeft)
    compact_layout.addStretch(1)
    panel_layout.addWidget(compact_row)

    panel_layout.addSpacing(6)
    section = QLabel("Filter / sort button concepts")
    section.setStyleSheet("font-weight: 700;")
    panel_layout.addWidget(section)

    sets_button = SetsFilterButton()
    panel_layout.addWidget(sets_button)

    sort_row = QWidget()
    sort_layout = QHBoxLayout(sort_row)
    sort_layout.setContentsMargins(0, 0, 0, 0)
    sort_layout.setSpacing(10)
    sort_layout.addWidget(QLabel("Sort button"))
    sort_button = SortCircleButton()
    sort_state = QLabel("off")
    sort_state.setObjectName("Muted")
    sort_button.clicked_with_state.connect(lambda checked: sort_state.setText("on" if checked else "off"))
    sort_layout.addWidget(sort_button)
    sort_layout.addWidget(sort_state)
    sort_layout.addStretch(1)
    panel_layout.addWidget(sort_row)

    plain_row = QWidget()
    plain_layout = QHBoxLayout(plain_row)
    plain_layout.setContentsMargins(0, 0, 0, 0)
    plain_layout.setSpacing(10)
    plain_layout.addWidget(QLabel("Plain matching toggle"))
    matching_toggle = ToggleSwitch()
    matching_toggle.setChecked(True)
    plain_layout.addWidget(matching_toggle)
    plain_layout.addStretch(1)
    panel_layout.addWidget(plain_row)

    root.addWidget(panel)
    window.resize(500, 430)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
