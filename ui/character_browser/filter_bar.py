from __future__ import annotations

from typing import Any

from PySide6.QtCore import QSize, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QWidget

from localization import tr
from ui.character_assets import (
    CHARACTER_RARITY_FILTERS,
    CHARACTER_STANDARD_FILTER,
    CHARACTER_TRAIT_FILTERS,
    ELEMENT_FILTERS,
    FILTER_ASSETS_DIR,
    STANDARD_FILTER_ALL,
    STANDARD_FILTER_EXCLUDE,
    STANDARD_FILTER_ONLY,
    WEAPON_TYPE_FILTERS,
    standard_character_filter_icon,
)
from ui.utils.filter_button_style import (
    FILTER_BUTTON_ICON_SIZE,
    FILTER_BUTTON_SIZE,
    filter_button_style,
)
from ui.utils.tooltips import install_custom_tooltip


_FILTER_BUTTON_STYLE = filter_button_style("app_shell_filter_button")


class CharacterFilterBar(QWidget):
    """Shared character filters used by normal roster and scoped browsers."""

    filters_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("character_filter_bar")
        self.element_filters: set[str] = set()
        self.weapon_filters: set[str] = set()
        self.rarity_filters: set[int] = set()
        self.trait_filters: set[str] = set()
        self.standard_filter = STANDARD_FILTER_ALL
        self.buttons: list[QPushButton] = []

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)
        for values, active_set in (
            (ELEMENT_FILTERS, self.element_filters),
            (WEAPON_TYPE_FILTERS, self.weapon_filters),
            (CHARACTER_RARITY_FILTERS, self.rarity_filters),
            (CHARACTER_TRAIT_FILTERS, self.trait_filters),
        ):
            for value, icon_name, tooltip_key in values:
                button = self._make_filter_button(
                    value=value,
                    icon_name=icon_name,
                    tooltip_key=tooltip_key,
                    active_set=active_set,
                )
                self.buttons.append(button)
                layout.addWidget(button)
        self.standard_button = self._make_standard_filter_button()
        self.buttons.append(self.standard_button)
        layout.addWidget(self.standard_button)
        layout.addStretch(1)

    def reset(self) -> None:
        self.element_filters.clear()
        self.weapon_filters.clear()
        self.rarity_filters.clear()
        self.trait_filters.clear()
        self.standard_filter = STANDARD_FILTER_ALL
        for button in self.buttons:
            button.blockSignals(True)
            button.setChecked(False)
            button.blockSignals(False)
        self._refresh_standard_button()
        self.filters_changed.emit()

    def _make_filter_button(
        self,
        *,
        value: Any,
        icon_name: str,
        tooltip_key: str,
        active_set: set[Any],
    ) -> QPushButton:
        button = _base_filter_button()
        icon_path = FILTER_ASSETS_DIR / icon_name
        if icon_path.exists():
            button.setIcon(QIcon(str(icon_path)))
        else:
            button.setText(str(value))
        install_custom_tooltip(button, tr(tooltip_key))

        def toggle_filter(checked: bool) -> None:
            if checked:
                active_set.add(value)
            else:
                active_set.discard(value)
            self.filters_changed.emit()

        button.clicked.connect(toggle_filter)
        return button

    def _make_standard_filter_button(self) -> QPushButton:
        _value, _icon_name, tooltip_key = CHARACTER_STANDARD_FILTER
        button = _base_filter_button(checkable=False)
        install_custom_tooltip(button, tr(tooltip_key))

        def cycle_standard_filter() -> None:
            if self.standard_filter == STANDARD_FILTER_ALL:
                self.standard_filter = STANDARD_FILTER_ONLY
            elif self.standard_filter == STANDARD_FILTER_ONLY:
                self.standard_filter = STANDARD_FILTER_EXCLUDE
            else:
                self.standard_filter = STANDARD_FILTER_ALL
            self._refresh_standard_button()
            self.filters_changed.emit()

        button.clicked.connect(cycle_standard_filter)
        self._refresh_standard_button(button)
        return button

    def _refresh_standard_button(self, button: QPushButton | None = None) -> None:
        target = button or self.standard_button
        target.setProperty("standardOnly", self.standard_filter == STANDARD_FILTER_ONLY)
        target.setProperty("standardExclude", self.standard_filter == STANDARD_FILTER_EXCLUDE)
        target.setIcon(
            standard_character_filter_icon(
                self.standard_filter,
                size=FILTER_BUTTON_ICON_SIZE,
            )
        )
        target.style().unpolish(target)
        target.style().polish(target)
        target.update()


def _base_filter_button(*, checkable: bool = True) -> QPushButton:
    button = QPushButton("")
    button.setObjectName("app_shell_filter_button")
    button.setCheckable(checkable)
    button.setFixedSize(FILTER_BUTTON_SIZE, FILTER_BUTTON_SIZE)
    button.setIconSize(QSize(FILTER_BUTTON_ICON_SIZE, FILTER_BUTTON_ICON_SIZE))
    button.setStyleSheet(_FILTER_BUTTON_STYLE)
    return button


__all__ = ["CharacterFilterBar"]
