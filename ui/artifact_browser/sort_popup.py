from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
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
QFrame#sort_option_row {
    border: 1px solid #343b49;
    border-radius: 7px;
    background: #222630;
}
QFrame#sort_option_row:hover {
    background: #2b303b;
}
QFrame#sort_option_row[selected="true"] {
    border-color: #d6b35f;
    background: #3a3224;
}
QFrame#sort_option_row QLabel {
    background: transparent;
}
QFrame#sort_option_row QLabel#sort_order {
    color: #f1d78a;
    font-weight: 700;
}
"""


class _SortOptionRow(QFrame):
    toggled = Signal(bool)

    def __init__(
        self,
        *,
        label: str,
        checked: bool,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setObjectName("sort_option_row")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self._checked = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 5, 8, 5)
        layout.setSpacing(8)

        self._label = QLabel(label)
        self._label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._label.setMinimumHeight(28)
        layout.addWidget(self._label, 1)

        self._order_label = QLabel("")
        self._order_label.setObjectName("sort_order")
        self._order_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._order_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self._order_label.setFixedWidth(28)
        layout.addWidget(self._order_label)

        self.setChecked(checked)

    def set_label(self, text: str) -> None:
        self._label.setText(text)

    def set_order_text(self, text: str) -> None:
        self._order_label.setText(text)

    def isChecked(self) -> bool:
        return self._checked

    def setChecked(self, checked: bool) -> None:
        checked = bool(checked)
        if self._checked == checked:
            return

        self._checked = checked
        self.setProperty("selected", checked)
        self.style().unpolish(self)
        self.style().polish(self)

    def toggle(self) -> None:
        self.setChecked(not self._checked)
        self.toggled.emit(self._checked)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            event.accept()
            return

        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self.rect().contains(event.position().toPoint())
        ):
            self.toggle()
            event.accept()
            return

        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.toggle()
            event.accept()
            return

        super().keyPressEvent(event)


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
        self._rows: dict[int, _SortOptionRow] = {}
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
            row = _SortOptionRow(
                label=tr(option.label_key),
                checked=option.property_type in self._selected_stat_types,
            )
            row.toggled.connect(
                lambda checked=False, property_type=option.property_type: (
                    self._on_stat_toggled(property_type, checked)
                )
            )
            self._rows[option.property_type] = row
            layout.addWidget(row)

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
                        self._rows[property_type].setChecked(False)
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
                row = self._rows[property_type]
                row.setChecked(property_type in self._selected_stat_types)

                label = tr(option.label_key)
                if property_type in self._selected_stat_types:
                    priority = self._selected_stat_types.index(property_type) + 1
                    row.set_order_text(str(priority))
                else:
                    row.set_order_text("")

                row.set_label(label)
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
