from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from localization import tr


REGION_POPUP_STYLE = """
QWidget#region_filter_popup {
    background: #1f222a;
    border: 1px solid #3d4350;
    border-radius: 8px;
}
QLabel {
    color: #eeeeee;
}
QLabel#muted {
    color: #aab0bd;
}
QPushButton {
    min-height: 24px;
    padding: 3px 8px;
    border: 1px solid #3d4350;
    border-radius: 6px;
    background: #222630;
    color: #eeeeee;
}
QPushButton:hover {
    background: #2b303b;
}
QPushButton#region_option {
    min-height: 58px;
    text-align: left;
    padding: 5px 8px;
}
QPushButton#region_option:checked {
    border-color: #d6b35f;
    background: #3a3224;
    color: #ffffff;
}
"""


class RegionFilterPopup(QWidget):
    def __init__(
        self,
        *,
        options: list[dict],
        selected_region_keys: set[str],
        on_selection_changed: Callable[[set[str]], None],
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setWindowFlag(Qt.WindowType.Popup, True)
        self.setObjectName("region_filter_popup")
        self.setStyleSheet(REGION_POPUP_STYLE)
        self.setMinimumSize(360, 320)
        self.resize(360, 360)

        self._options = list(options)
        self._selected_region_keys = set(selected_region_keys)
        self._on_selection_changed = on_selection_changed
        self._buttons: dict[str, QPushButton] = {}
        self._updating = False

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        header = QHBoxLayout()
        title = QLabel(tr("filter.region.title"))
        title.setStyleSheet("font-weight: 700;")
        header.addWidget(title)
        header.addStretch()

        close_button = QPushButton("X")
        close_button.setFixedWidth(28)
        close_button.clicked.connect(self.close)
        header.addWidget(close_button)
        root.addLayout(header)

        if not self._options:
            empty = QLabel(tr("filter.region.empty"))
            empty.setObjectName("muted")
            empty.setWordWrap(True)
            root.addWidget(empty, 1)
        else:
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.Shape.NoFrame)

            content = QWidget()
            grid = QGridLayout(content)
            grid.setContentsMargins(0, 0, 0, 0)
            grid.setHorizontalSpacing(6)
            grid.setVerticalSpacing(6)

            for index, option in enumerate(self._options):
                button = self._make_region_button(option)
                row = index // 2
                col = index % 2
                grid.addWidget(button, row, col)

            grid.setRowStretch((len(self._options) + 1) // 2, 1)
            scroll.setWidget(content)
            root.addWidget(scroll, 1)

        bottom = QHBoxLayout()
        bottom.addStretch()

        clear_button = QPushButton(tr("filter.region.clear"))
        clear_button.clicked.connect(self.clear_selection)
        bottom.addWidget(clear_button)
        root.addLayout(bottom)

    def _make_region_button(self, option: dict) -> QPushButton:
        key = str(option.get("key") or "")
        count = int(option.get("count") or 0)
        text = str(option.get("name") or key)
        if count > 0:
            text = f"{text} ({count})"

        button = QPushButton(text)
        button.setObjectName("region_option")
        button.setCheckable(True)
        button.setChecked(key in self._selected_region_keys)

        icon_path = option.get("icon_path")
        if icon_path:
            button.setIcon(QIcon(str(icon_path)))
            button.setIconSize(QSize(30, 30))

        button.clicked.connect(
            lambda checked=False, region_key=key: self._on_region_toggled(region_key, checked)
        )
        self._buttons[key] = button
        return button

    def _on_region_toggled(self, region_key: str, checked: bool) -> None:
        if self._updating:
            return

        if checked:
            self._selected_region_keys.add(region_key)
        else:
            self._selected_region_keys.discard(region_key)

        self._on_selection_changed(set(self._selected_region_keys))

    def set_selected_region_keys(self, selected_region_keys: set[str]) -> None:
        self._updating = True
        self._selected_region_keys = set(selected_region_keys)
        for key, button in self._buttons.items():
            button.setChecked(key in self._selected_region_keys)
        self._updating = False

    def clear_selection(self) -> None:
        self._updating = True
        self._selected_region_keys.clear()
        for button in self._buttons.values():
            button.setChecked(False)
        self._updating = False
        self._on_selection_changed(set())
