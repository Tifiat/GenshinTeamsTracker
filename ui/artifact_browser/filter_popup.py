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
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .store import ArtifactSetOption, CustomSetOption


POPUP_STYLE = """
QWidget#sets_filter_popup {
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
QTabWidget::pane {
    border: 1px solid #303642;
    border-radius: 6px;
}
QTabBar::tab {
    padding: 5px 10px;
    background: #222630;
    color: #d8d8d8;
    border: 1px solid #303642;
    border-bottom: none;
}
QTabBar::tab:selected {
    background: #303848;
    color: #ffffff;
}
QCheckBox {
    color: #eeeeee;
    spacing: 8px;
}
"""


class SetsFilterPopup(QWidget):
    def __init__(
        self,
        *,
        game_sets: list[ArtifactSetOption],
        custom_sets: list[CustomSetOption],
        selected_game_set_ids: set[int | None],
        selected_custom_set_ids: set[int],
        on_selection_changed: Callable[[set[int | None], set[int]], None],
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setWindowFlag(Qt.WindowType.Popup, True)
        self.setObjectName("sets_filter_popup")
        self.setStyleSheet(POPUP_STYLE)
        self.setMinimumSize(360, 420)

        self._on_selection_changed = on_selection_changed
        self._game_checkboxes: dict[int | None, QCheckBox] = {}
        self._custom_checkboxes: dict[int, QCheckBox] = {}
        self._updating = False

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        header = QHBoxLayout()
        title = QLabel("Наборы")
        title.setStyleSheet("font-weight: 700;")
        header.addWidget(title)
        header.addStretch()

        close_button = QPushButton("×")
        close_button.setFixedWidth(28)
        close_button.clicked.connect(self.close)
        header.addWidget(close_button)
        root.addLayout(header)

        tabs = QTabWidget()
        tabs.addTab(
            self._build_game_sets_tab(game_sets, selected_game_set_ids),
            "Игровые",
        )
        tabs.addTab(
            self._build_custom_sets_tab(custom_sets, selected_custom_set_ids),
            "Свои",
        )
        root.addWidget(tabs, 1)

        bottom = QHBoxLayout()
        bottom.addStretch()

        clear_button = QPushButton("Сбросить выбор")
        clear_button.clicked.connect(self.clear_selection)
        bottom.addWidget(clear_button)

        root.addLayout(bottom)

    def _build_game_sets_tab(
        self,
        options: list[ArtifactSetOption],
        selected_ids: set[int | None],
    ) -> QWidget:
        return self._build_scroll_tab(
            empty_text="Игровые наборы не найдены.",
            rows=[
                (
                    option.set_id,
                    option.set_name,
                    option.count,
                    option.set_id in selected_ids,
                )
                for option in options
            ],
            target=self._game_checkboxes,
        )

    def _build_custom_sets_tab(
        self,
        options: list[CustomSetOption],
        selected_ids: set[int],
    ) -> QWidget:
        return self._build_scroll_tab(
            empty_text="Своих наборов пока нет.",
            rows=[
                (
                    option.tag_id,
                    option.name,
                    option.count,
                    option.tag_id in selected_ids,
                )
                for option in options
            ],
            target=self._custom_checkboxes,
        )

    def _build_scroll_tab(
        self,
        *,
        empty_text: str,
        rows: list[tuple[object, str, int, bool]],
        target: dict,
    ) -> QWidget:
        outer = QWidget()
        outer_layout = QVBoxLayout(outer)
        outer_layout.setContentsMargins(8, 8, 8, 8)
        outer_layout.setSpacing(6)

        if not rows:
            label = QLabel(empty_text)
            label.setObjectName("muted")
            label.setWordWrap(True)
            outer_layout.addWidget(label)
            outer_layout.addStretch()
            return outer

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        for key, name, count, checked in rows:
            checkbox = QCheckBox(f"{name}  ({count})")
            checkbox.setChecked(checked)
            checkbox.toggled.connect(self._emit_selection_changed)
            target[key] = checkbox
            layout.addWidget(checkbox)

        layout.addStretch()
        scroll.setWidget(content)
        outer_layout.addWidget(scroll, 1)

        return outer

    def _emit_selection_changed(self) -> None:
        if self._updating:
            return

        self._on_selection_changed(
            self.selected_game_set_ids(),
            self.selected_custom_set_ids(),
        )

    def selected_game_set_ids(self) -> set[int | None]:
        return {
            set_id
            for set_id, checkbox in self._game_checkboxes.items()
            if checkbox.isChecked()
        }

    def selected_custom_set_ids(self) -> set[int]:
        return {
            tag_id
            for tag_id, checkbox in self._custom_checkboxes.items()
            if checkbox.isChecked()
        }

    def clear_selection(self) -> None:
        self._updating = True
        try:
            for checkbox in self._game_checkboxes.values():
                checkbox.setChecked(False)
            for checkbox in self._custom_checkboxes.values():
                checkbox.setChecked(False)
        finally:
            self._updating = False

        self._emit_selection_changed()