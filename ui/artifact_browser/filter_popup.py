from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QLineEdit,
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

from localization import tr

from .store import ArtifactSetOption, CustomSetOption
from hoyolab_export.paths import PROJECT_ROOT

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
    spacing: 10px;
    padding: 5px 4px;
    min-height: 42px;
}
QCheckBox::indicator {
    width: 18px;
    height: 18px;
}
QLineEdit[invalid="true"] {
    border: 1px solid #d66a6a;
    background: #3a2428;
    color: #ffffff;
}
"""


class SetsFilterPopup(QWidget):
    def __init__(
        self,
        *,
        game_sets: list[ArtifactSetOption],
        custom_sets: list[CustomSetOption],
        selected_game_set_ids: set[str],
        selected_custom_set_ids: set[int],
        on_selection_changed: Callable[[set[str], set[int]], None],
        parent: QWidget | None = None,
        on_custom_set_create: Callable[[str], None],
        on_custom_set_edit: Callable[[int], None],
        on_custom_set_delete: Callable[[int], list[CustomSetOption]],
    ):
        super().__init__(parent)
        self.setWindowFlag(Qt.WindowType.Popup, True)
        self.setObjectName("sets_filter_popup")
        self.setStyleSheet(POPUP_STYLE)
        self.setMinimumSize(500, 560)
        self.resize(500, 560)

        self._on_selection_changed = on_selection_changed
        self._on_custom_set_create = on_custom_set_create
        self._on_custom_set_edit = on_custom_set_edit
        self._on_custom_set_delete = on_custom_set_delete
        self._pending_delete_tag_id: int | None = None
        self._custom_sets = list(custom_sets)
        self._custom_selected_ids = set(selected_custom_set_ids)
        self._custom_list_layout: QVBoxLayout | None = None
        self._game_checkboxes: dict[str, QCheckBox] = {}
        self._custom_checkboxes: dict[int, QCheckBox] = {}
        self._updating = False

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        header = QHBoxLayout()
        title = QLabel(tr("artifact.sets.title"))
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
            tr("artifact.sets.tab.game"),
        )
        tabs.addTab(
            self._build_custom_sets_tab(custom_sets, selected_custom_set_ids),
            tr("artifact.sets.tab.custom"),
        )
        root.addWidget(tabs, 1)

        bottom = QHBoxLayout()
        bottom.addStretch()

        clear_button = QPushButton(tr("artifact.sets.clear"))
        clear_button.clicked.connect(self.clear_selection)
        bottom.addWidget(clear_button)

        root.addLayout(bottom)

    @staticmethod
    def _ui_icon(name: str) -> QIcon:
        return QIcon(str(PROJECT_ROOT / "assets" / "ui" / "icons" / f"{name}.svg"))

    def _icon_button(self, icon_name: str, tooltip: str) -> QPushButton:
        button = QPushButton()
        button.setIcon(self._ui_icon(icon_name))
        button.setToolTip(tooltip)
        button.setFixedWidth(30)
        return button

    def _build_game_sets_tab(
        self,
        options: list[ArtifactSetOption],
        selected_ids: set[str],
    ) -> QWidget:
        return self._build_scroll_tab(
            empty_text=tr("artifact.sets.empty_game"),
            rows=[
                (
                    option.set_uid,
                    option.set_name,
                    option.count,
                    option.set_uid in selected_ids,
                    option.icon_path,
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
        outer = QWidget()
        outer_layout = QVBoxLayout(outer)
        outer_layout.setContentsMargins(8, 8, 8, 8)
        outer_layout.setSpacing(6)

        create_row = QHBoxLayout()
        self._new_custom_set_input = QLineEdit()
        self._new_custom_set_input.setPlaceholderText(
            tr("artifact.custom.name_placeholder")
        )
        self._new_custom_set_input.returnPressed.connect(self._create_custom_set)
        self._new_custom_set_input.textChanged.connect(self._clear_create_invalid)
        create_row.addWidget(self._new_custom_set_input, 1)

        create_button = self._icon_button(
            "plus",
            tr("artifact.custom.create"),
        )
        create_button.clicked.connect(self._create_custom_set)
        create_row.addWidget(create_button)

        outer_layout.addLayout(create_row)

        self._custom_list_layout = QVBoxLayout()
        self._custom_list_layout.setContentsMargins(0, 0, 0, 0)
        self._custom_list_layout.setSpacing(0)
        outer_layout.addLayout(self._custom_list_layout, 1)
        self._refresh_custom_rows()

        return outer

    def _refresh_custom_rows(self) -> None:
        if self._custom_list_layout is None:
            return

        if self._custom_checkboxes:
            self._custom_selected_ids = self.selected_custom_set_ids()
        self._custom_checkboxes.clear()
        self._clear_layout(self._custom_list_layout)

        if not self._custom_sets:
            label = QLabel(tr("artifact.sets.empty_custom"))
            label.setObjectName("muted")
            label.setWordWrap(True)
            self._custom_list_layout.addWidget(label)
            self._custom_list_layout.addStretch()
            return

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        for option in self._custom_sets:
            row = QHBoxLayout()

            checkbox = QCheckBox(f"{option.name}  ({option.count})")
            checkbox.setMinimumHeight(40)
            checkbox.blockSignals(True)
            checkbox.setChecked(option.tag_id in self._custom_selected_ids)
            checkbox.blockSignals(False)
            checkbox.toggled.connect(self._emit_selection_changed)
            self._custom_checkboxes[option.tag_id] = checkbox
            row.addWidget(checkbox, 1)

            edit_button = self._icon_button(
                "edit",
                tr("artifact.custom.edit"),
            )
            edit_button.clicked.connect(
                lambda _checked=False, tag_id=option.tag_id: self._on_custom_set_edit(tag_id)
            )
            row.addWidget(edit_button)

            if self._pending_delete_tag_id == option.tag_id:
                confirm_label = QLabel(tr("artifact.custom.delete_confirm_short"))
                confirm_label.setObjectName("muted")
                row.addWidget(confirm_label)

                confirm_button = self._icon_button(
                    "check",
                    tr("artifact.custom.delete"),
                )
                confirm_button.clicked.connect(
                    lambda _checked=False, tag_id=option.tag_id: self._confirm_delete(tag_id)
                )
                row.addWidget(confirm_button)

                cancel_button = self._icon_button(
                    "x",
                    tr("artifact.custom.cancel"),
                )
                cancel_button.clicked.connect(self._clear_pending_delete)
                row.addWidget(cancel_button)
            else:
                delete_button = self._icon_button(
                    "delete",
                    tr("artifact.custom.delete"),
                )
                delete_button.clicked.connect(
                    lambda _checked=False, tag_id=option.tag_id: self._request_delete(tag_id)
                )
                row.addWidget(delete_button)

            layout.addLayout(row)

        layout.addStretch()
        scroll.setWidget(content)
        self._custom_list_layout.addWidget(scroll, 1)

    def _clear_layout(self, layout: QVBoxLayout | QHBoxLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            child_layout = item.layout()
            if widget is not None:
                widget.deleteLater()
            if child_layout is not None:
                self._clear_layout(child_layout)

    def _build_scroll_tab(
        self,
        *,
        empty_text: str,
        rows: list[tuple[object, str, int, bool, object]],
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

        for key, name, count, checked, icon_path in rows:
            checkbox = QCheckBox(f"{name}  ({count})")
            checkbox.setMinimumHeight(44)

            if icon_path:
                checkbox.setIcon(QIcon(str(icon_path)))
                checkbox.setIconSize(QSize(36, 36))

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

    def selected_game_set_ids(self) -> set[str]:
        return {
            set_uid
            for set_uid, checkbox in self._game_checkboxes.items()
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

    def _create_custom_set(self) -> None:
        name = self._new_custom_set_input.text().strip()
        if not name:
            self._new_custom_set_input.setProperty("invalid", True)
            self._new_custom_set_input.setPlaceholderText(
                tr("artifact.custom.enter_name")
            )
            self._new_custom_set_input.style().unpolish(self._new_custom_set_input)
            self._new_custom_set_input.style().polish(self._new_custom_set_input)
            return

        self._on_custom_set_create(name)

    def _clear_create_invalid(self) -> None:
        if not self._new_custom_set_input.property("invalid"):
            return

        self._new_custom_set_input.setProperty("invalid", False)
        self._new_custom_set_input.setPlaceholderText(
            tr("artifact.custom.name_placeholder")
        )
        self._new_custom_set_input.style().unpolish(self._new_custom_set_input)
        self._new_custom_set_input.style().polish(self._new_custom_set_input)

    def _request_delete(self, tag_id: int) -> None:
        self._pending_delete_tag_id = tag_id
        self._refresh_custom_rows()

    def _confirm_delete(self, tag_id: int) -> None:
        self._custom_selected_ids = self.selected_custom_set_ids()
        self._custom_selected_ids.discard(tag_id)
        self._custom_sets = self._on_custom_set_delete(tag_id)
        self._pending_delete_tag_id = None
        self._refresh_custom_rows()

    def _clear_pending_delete(self) -> None:
        self._pending_delete_tag_id = None
        self._refresh_custom_rows()
