from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QLineEdit,
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
from ui.utils.icon_utils import auto_contrast_svg_icon

from .store import ArtifactSetOption, CustomSetOption

UI_ICON_BUTTON_BACKGROUND = "#222630"
UI_ICON_DEFAULT_SIZE = 24

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
QPushButton#row_save_button,
QPushButton#row_cancel_button {
    min-width: 30px;
    max-width: 30px;
    min-height: 24px;
    max-height: 24px;
    padding: 2px;
}
QPushButton#row_save_button {
    border-color: #4e9b61;
    background: #24452d;
}
QPushButton#row_save_button:hover {
    background: #2d5938;
}
QPushButton#row_cancel_button {
    border-color: #b85b5b;
    background: #4a2529;
}
QPushButton#row_cancel_button:hover {
    background: #5c2d32;
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
QFrame#set_filter_row {
    border: 1px solid #343b49;
    border-radius: 7px;
    background: #222630;
}
QFrame#set_filter_row:hover {
    background: #2b303b;
}
QFrame#set_filter_row[selected="true"] {
    border-color: #d6b35f;
    background: #3a3224;
}
QFrame#set_filter_row QLabel {
    background: transparent;
}
QFrame#set_filter_row QLabel#set_count {
    color: #aab0bd;
    font-weight: 600;
}
QFrame#set_filter_row[selected="true"] QLabel#set_count {
    color: #f1d78a;
}
QLineEdit[invalid="true"] {
    border: 1px solid #d66a6a;
    background: #3a2428;
    color: #ffffff;
}
"""


class _SetSelectionRow(QFrame):
    toggled = Signal(bool)

    def __init__(
        self,
        *,
        name: str,
        count: int,
        checked: bool,
        icon_path: object | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setObjectName("set_filter_row")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self._checked = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 5, 8, 5)
        layout.setSpacing(8)

        if icon_path:
            icon_label = QLabel()
            icon_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            icon_label.setFixedSize(36, 36)
            icon_label.setPixmap(
                QIcon(str(icon_path)).pixmap(QSize(36, 36))
            )
            layout.addWidget(icon_label)

        name_label = QLabel(name)
        name_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        name_label.setMinimumHeight(28)
        layout.addWidget(name_label, 1)

        count_label = QLabel(f"({count})")
        count_label.setObjectName("set_count")
        count_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        count_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        count_label.setFixedWidth(52)
        layout.addWidget(count_label)

        self._trailing_layout = QHBoxLayout()
        self._trailing_layout.setContentsMargins(0, 0, 0, 0)
        self._trailing_layout.setSpacing(5)
        layout.addLayout(self._trailing_layout)

        self.setChecked(checked)

    def add_trailing_widget(self, widget: QWidget) -> None:
        self._trailing_layout.addWidget(widget)

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
        self._game_rows: dict[str, _SetSelectionRow] = {}
        self._custom_rows: dict[int, _SetSelectionRow] = {}
        self._updating = False
        self._pending_delete_shortcuts: list[QShortcut] = []

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
        self._init_pending_delete_shortcuts()

    @staticmethod
    def _ui_icon(name: str) -> QIcon:
        return auto_contrast_svg_icon(
            name,
            UI_ICON_DEFAULT_SIZE,
            UI_ICON_BUTTON_BACKGROUND,
        )

    def _icon_button(self, icon_name: str, tooltip: str) -> QPushButton:
        button = QPushButton()
        button.setIcon(self._ui_icon(icon_name))
        button.setToolTip(tooltip)
        button.setFixedWidth(30)
        return button

    def _apply_icon_button_role(self, button: QPushButton, object_name: str) -> None:
        button.setObjectName(object_name)
        button.setFixedSize(30, 24)
        button.style().unpolish(button)
        button.style().polish(button)

    def _init_pending_delete_shortcuts(self) -> None:
        for key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            shortcut.activated.connect(self._confirm_pending_delete_shortcut)
            shortcut.setEnabled(False)
            self._pending_delete_shortcuts.append(shortcut)

        cancel_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        cancel_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        cancel_shortcut.activated.connect(self._cancel_pending_delete_shortcut)
        cancel_shortcut.setEnabled(False)
        self._pending_delete_shortcuts.append(cancel_shortcut)

    def _set_pending_delete_shortcuts_enabled(self, enabled: bool) -> None:
        for shortcut in self._pending_delete_shortcuts:
            shortcut.setEnabled(enabled)

    def _confirm_pending_delete_shortcut(self) -> None:
        if self._pending_delete_tag_id is not None:
            self._confirm_delete(self._pending_delete_tag_id)

    def _cancel_pending_delete_shortcut(self) -> None:
        if self._pending_delete_tag_id is not None:
            self._clear_pending_delete()

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
                for option in sorted(
                    options,
                    key=lambda item: (-item.count, item.set_name.casefold()),
                )
            ],
            target=self._game_rows,
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

        if self._custom_rows:
            self._custom_selected_ids = self.selected_custom_set_ids()
        self._custom_rows.clear()
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

        for option in sorted(
            self._custom_sets,
            key=lambda item: (-item.count, item.name.casefold()),
        ):
            row = _SetSelectionRow(
                name=option.name,
                count=option.count,
                checked=option.tag_id in self._custom_selected_ids,
            )
            row.toggled.connect(self._emit_selection_changed)
            self._custom_rows[option.tag_id] = row

            edit_button = self._icon_button(
                "edit",
                tr("artifact.custom.edit"),
            )
            edit_button.clicked.connect(
                lambda _checked=False, tag_id=option.tag_id: self._on_custom_set_edit(tag_id)
            )
            row.add_trailing_widget(edit_button)

            if self._pending_delete_tag_id == option.tag_id:
                confirm_label = QLabel(tr("artifact.custom.delete_confirm_short"))
                confirm_label.setObjectName("muted")
                row.add_trailing_widget(confirm_label)

                confirm_button = self._icon_button(
                    "check",
                    tr("artifact.custom.delete"),
                )
                self._apply_icon_button_role(confirm_button, "row_save_button")
                confirm_button.clicked.connect(
                    lambda _checked=False, tag_id=option.tag_id: self._confirm_delete(tag_id)
                )
                row.add_trailing_widget(confirm_button)

                cancel_button = self._icon_button(
                    "x",
                    tr("artifact.custom.cancel"),
                )
                self._apply_icon_button_role(cancel_button, "row_cancel_button")
                cancel_button.clicked.connect(self._clear_pending_delete)
                row.add_trailing_widget(cancel_button)
            else:
                delete_button = self._icon_button(
                    "delete",
                    tr("artifact.custom.delete"),
                )
                delete_button.clicked.connect(
                    lambda _checked=False, tag_id=option.tag_id: self._request_delete(tag_id)
                )
                row.add_trailing_widget(delete_button)

            layout.addWidget(row)

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
            row = _SetSelectionRow(
                name=name,
                count=count,
                checked=checked,
                icon_path=icon_path,
            )
            row.toggled.connect(self._emit_selection_changed)
            target[key] = row
            layout.addWidget(row)

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
            for set_uid, row in self._game_rows.items()
            if row.isChecked()
        }

    def selected_custom_set_ids(self) -> set[int]:
        return {
            tag_id
            for tag_id, row in self._custom_rows.items()
            if row.isChecked()
        }

    def clear_selection(self) -> None:
        self._updating = True
        try:
            for row in self._game_rows.values():
                row.setChecked(False)
            for row in self._custom_rows.values():
                row.setChecked(False)
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
        self._set_pending_delete_shortcuts_enabled(True)
        self._refresh_custom_rows()

    def _confirm_delete(self, tag_id: int) -> None:
        self._custom_selected_ids = self.selected_custom_set_ids()
        self._custom_selected_ids.discard(tag_id)
        self._custom_sets = self._on_custom_set_delete(tag_id)
        self._pending_delete_tag_id = None
        self._set_pending_delete_shortcuts_enabled(False)
        self._refresh_custom_rows()

    def _clear_pending_delete(self) -> None:
        self._pending_delete_tag_id = None
        self._set_pending_delete_shortcuts_enabled(False)
        self._refresh_custom_rows()

    def keyPressEvent(self, event) -> None:
        if self._pending_delete_tag_id is not None:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._confirm_delete(self._pending_delete_tag_id)
                event.accept()
                return
            if event.key() == Qt.Key.Key_Escape:
                self._clear_pending_delete()
                event.accept()
                return

        super().keyPressEvent(event)
