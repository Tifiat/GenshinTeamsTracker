from __future__ import annotations

from PySide6.QtCore import QSignalBlocker, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPainter
from PySide6.QtWidgets import QBoxLayout, QPushButton, QWidget

from localization import tr
from ui.character_browser.sorting import CHARACTER_SORT_MODE_COUNTS, DEFAULT_CHARACTER_SORT
from ui.utils.filter_button_style import FILTER_BUTTON_ICON_SIZE, FILTER_BUTTON_SIZE, filter_button_style
from ui.utils.icon_utils import tinted_svg_pixmap
from ui.utils.tooltips import install_custom_tooltip
from ui.utils.ui_palette import UI_BG_PANEL, UI_TEXT_PRIMARY


def character_filter_hint(tooltip_key: str) -> str:
    """Keep the same predicate/conflict explanation on every character filter."""
    return f"{tr(tooltip_key)}\n\n{tr('filter.character.rules')}"


class CharacterSortControls(QWidget):
    """Two exclusive cycling sorts; state belongs to this browser, not the account."""

    sort_changed = Signal()

    def __init__(
        self, parent: QWidget | None = None, *, vertical: bool = False,
        button_name: str = "app_shell_filter_button",
        context_hint_key: str | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("character_sort_controls")
        self.state = DEFAULT_CHARACTER_SORT
        self.context_hint_key = context_hint_key
        self.buttons: dict[str, QPushButton] = {}
        layout = QBoxLayout(QBoxLayout.Direction.TopToBottom if vertical else QBoxLayout.Direction.LeftToRight, self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)
        for criterion in CHARACTER_SORT_MODE_COUNTS:
            button = QPushButton(self)
            button.setObjectName(button_name)
            button.setCheckable(True)
            button.setFixedSize(FILTER_BUTTON_SIZE, FILTER_BUTTON_SIZE)
            button.setIconSize(QSize(FILTER_BUTTON_ICON_SIZE, FILTER_BUTTON_ICON_SIZE))
            button.setStyleSheet(filter_button_style(button_name))
            button.clicked.connect(lambda _checked=False, kind=criterion: self.advance(kind))
            self.buttons[criterion] = button
            layout.addWidget(button)
        self.constellation_button = self.buttons["constellation"]
        self.level_button = self.buttons["level"]
        self.retranslate_ui()

    def advance(self, criterion: str) -> None:
        self.state = self.state.next(criterion)
        self.retranslate_ui()
        self.sort_changed.emit()

    def reset(self, *, emit: bool = True) -> None:
        self.state = DEFAULT_CHARACTER_SORT
        self.retranslate_ui()
        if emit:
            self.sort_changed.emit()

    def retranslate_ui(self) -> None:
        for criterion, button in self.buttons.items():
            mode = self.state.mode if self.state.criterion == criterion else 0
            with QSignalBlocker(button):
                button.setChecked(mode != 0)
            button.setProperty("sortMode", mode)
            button.setAccessibleName(tr(f"filter.sort.{criterion}.title"))
            button.setIcon(_sort_icon(criterion, mode))
            lines = [tr(f"filter.sort.{criterion}.title"), tr("filter.sort.current", mode=mode), ""]
            lines.extend(
                f"{number}: {tr('filter.sort.off') if number == 0 else tr(f'filter.sort.{criterion}.{number}')}"
                for number in range(CHARACTER_SORT_MODE_COUNTS[criterion] + 1)
            )
            lines.extend(["", tr("filter.sort.rules")])
            if self.context_hint_key:
                lines.extend(["", tr(self.context_hint_key)])
            install_custom_tooltip(button, "\n".join(lines))


def _sort_icon(criterion: str, mode: int) -> QIcon:
    pixmap = tinted_svg_pixmap(f"character-{criterion}", size=FILTER_BUTTON_ICON_SIZE, color=UI_TEXT_PRIMARY).copy()
    if mode:
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(UI_BG_PANEL))
        painter.drawRoundedRect(13, 13, 11, 11, 3, 3)
        font = QFont()
        font.setPixelSize(10)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(UI_TEXT_PRIMARY))
        painter.drawText(13, 13, 11, 11, Qt.AlignmentFlag.AlignCenter, str(mode))
        painter.end()
    return QIcon(pixmap)


__all__ = ["CharacterSortControls", "character_filter_hint"]
