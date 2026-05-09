from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from localization import tr

from .stat_types import sortable_stat_options


SORT_POPUP_STYLE = """
QWidget#sort_popup {
    background: #1f222a;
    border: 1px solid #3d4350;
    border-radius: 10px;
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
QCheckBox {
    color: #eeeeee;
    spacing: 10px;
    padding: 5px 4px;
    min-height: 34px;
}
QCheckBox::indicator {
    width: 18px;
    height: 18px;
}
"""


class SortStatsPopup(QWidget):
    def __init__(
        self,
        *,
        selected_stat_types: list[int],
        on_selection_changed: Callable[[list[int]], None],
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setWindowFlag(Qt.WindowType.Popup, True)
        self.setObjectName("sort_popup")
        self.setStyleSheet(SORT_POPUP_STYLE)
        self.setMinimumSize(360, 520)
        self.resize(360, 520)

        self._on_selection_changed = on_selection_changed
        self._selected_stat_types = list(selected_stat_types[:4])
        self._checkboxes: dict[int, QCheckBox] = {}
        self._updating = False

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        header = QHBoxLayout()
        title = QLabel(tr("artifact.sort.title"))
        title.setStyleSheet("font-weight: 700;")
        header.addWidget(title)
        header.addStretch()

        close_button = QPushButton("×")
        close_button.setFixedWidth(28)
        close_button.clicked.connect(self.close)
        header.addWidget(close_button)
        root.addLayout(header)

        self.limit_label = QLabel("")
        self.limit_label.setObjectName("muted")
        self.limit_label.setWordWrap(True)
        root.addWidget(self.limit_label)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        for option in sortable_stat_options():
            checkbox = QCheckBox()
            checkbox.setMinimumHeight(36)
            checkbox.setChecked(option.property_type in self._selected_stat_types)
            checkbox.toggled.connect(
                lambda checked=False, property_type=option.property_type: (
                    self._on_stat_toggled(property_type, checked)
                )
            )
            self._checkboxes[option.property_type] = checkbox
            layout.addWidget(checkbox)

        layout.addStretch()
        scroll.setWidget(content)
        root.addWidget(scroll, 1)

        bottom = QHBoxLayout()
        bottom.addStretch()

        clear_button = QPushButton(tr("artifact.sort.clear"))
        clear_button.clicked.connect(self.clear_selection)
        bottom.addWidget(clear_button)

        root.addLayout(bottom)

        self._refresh_labels()

    def _on_stat_toggled(self, property_type: int, checked: bool) -> None:
        if self._updating:
            return

        selected = list(self._selected_stat_types)

        if checked:
            if property_type not in selected:
                if len(selected) >= 4:
                    self._updating = True
                    try:
                        self._checkboxes[property_type].setChecked(False)
                    finally:
                        self._updating = False
                    self.limit_label.setText(tr("artifact.sort.limit"))
                    return

                selected.append(property_type)
        else:
            selected = [
                value
                for value in selected
                if value != property_type
            ]

        self._selected_stat_types = selected
        self.limit_label.setText(
            tr("artifact.sort.empty")
            if not self._selected_stat_types
            else tr("artifact.sort.limit")
        )
        self._refresh_labels()
        self._on_selection_changed(list(self._selected_stat_types))

    def _refresh_labels(self) -> None:
        self._updating = True
        try:
            for option in sortable_stat_options():
                property_type = option.property_type
                checkbox = self._checkboxes[property_type]
                checkbox.setChecked(property_type in self._selected_stat_types)

                label = tr(option.label_key)
                if property_type in self._selected_stat_types:
                    priority = self._selected_stat_types.index(property_type) + 1
                    label = f"{priority}. {label}"

                checkbox.setText(label)
        finally:
            self._updating = False

        self.limit_label.setText(
            tr("artifact.sort.empty")
            if not self._selected_stat_types
            else tr("artifact.sort.limit")
        )

    def selected_stat_types(self) -> list[int]:
        return list(self._selected_stat_types)

    def clear_selection(self) -> None:
        self._selected_stat_types = []
        self._refresh_labels()
        self._on_selection_changed([])