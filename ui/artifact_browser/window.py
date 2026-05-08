from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, QSize
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListView,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .card_delegate import ArtifactCardDelegate, GRID_SIZE
from .filter_popup import SetsFilterPopup
from .list_model import ArtifactListModel
from .models import ARTIFACT_POSITIONS
from .store import ArtifactBrowserStore


WINDOW_STYLE = """
QWidget {
    background: #17191f;
    color: #eeeeee;
    font-size: 13px;
}
QPushButton {
    min-height: 28px;
    padding: 4px 10px;
    border: 1px solid #3d4350;
    border-radius: 8px;
    background: #222630;
    color: #eeeeee;
}
QPushButton:hover {
    background: #2b303b;
}
QPushButton:checked {
    border-color: #7da7ff;
    background: #303848;
    color: #ffffff;
    font-weight: 600;
}
QPushButton#filter_switch {
    min-width: 42px;
    max-width: 42px;
}
QPushButton#filter_switch:checked {
    border-color: #7da7ff;
    background: #30415f;
}
QPushButton#sets_button {
    min-width: 110px;
}
QPushButton#close_button {
    min-width: 90px;
}
QLabel#status_label {
    color: #aab0bd;
}
QFrame#top_bar {
    border: 1px solid #2b3039;
    border-radius: 10px;
    background: #1f222a;
}
QListView {
    border: none;
    outline: none;
    background: #17191f;
}
QListView::item {
    background: transparent;
}
"""


class ArtifactBrowserWindow(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowFlag(Qt.Window, True)
        self.setWindowTitle("Артефакты")
        self.resize(1180, 760)
        self.setStyleSheet(WINDOW_STYLE)

        self.current_pos = 1
        self.store = ArtifactBrowserStore.load_from_db()
        self.model = ArtifactListModel(self.store, self)
        self.delegate = ArtifactCardDelegate(self)

        self.sets_filter_enabled = True
        self.selected_game_set_ids: set[int | None] = set()
        self.selected_custom_set_ids: set[int] = set()
        self._sets_popup: SetsFilterPopup | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        self._build_top_bar(root)
        self._build_list_view(root)
        self._build_bottom_bar(root)

        self.apply_current_filters()

    def _build_top_bar(self, root: QVBoxLayout) -> None:
        top_frame = QFrame()
        top_frame.setObjectName("top_bar")

        top = QHBoxLayout(top_frame)
        top.setContentsMargins(8, 8, 8, 8)
        top.setSpacing(6)

        self.slot_group = QButtonGroup(self)
        self.slot_group.setExclusive(True)

        for pos, label in ARTIFACT_POSITIONS.items():
            button = QPushButton(label)
            button.setCheckable(True)
            button.clicked.connect(lambda _checked=False, value=pos: self.set_position(value))
            self.slot_group.addButton(button, pos)
            top.addWidget(button)

            if pos == 1:
                button.setChecked(True)

        top.addStretch()

        self.sets_filter_switch = QPushButton("ON")
        self.sets_filter_switch.setObjectName("filter_switch")
        self.sets_filter_switch.setCheckable(True)
        self.sets_filter_switch.setChecked(True)
        self.sets_filter_switch.clicked.connect(self.on_sets_filter_enabled_changed)
        top.addWidget(self.sets_filter_switch)

        self.sets_button = QPushButton("Наборы")
        self.sets_button.setObjectName("sets_button")
        self.sets_button.clicked.connect(self.show_sets_popup)
        top.addWidget(self.sets_button)

        self.status_label = QLabel("")
        self.status_label.setObjectName("status_label")
        top.addWidget(self.status_label)

        root.addWidget(top_frame)

    def _build_list_view(self, root: QVBoxLayout) -> None:
        self.list_view = QListView()
        self.list_view.setModel(self.model)
        self.list_view.setItemDelegate(self.delegate)
        self.list_view.setViewMode(QListView.ViewMode.IconMode)
        self.list_view.setFlow(QListView.Flow.LeftToRight)
        self.list_view.setWrapping(True)
        self.list_view.setResizeMode(QListView.ResizeMode.Adjust)
        self.list_view.setMovement(QListView.Movement.Static)
        self.list_view.setUniformItemSizes(True)
        self.list_view.setGridSize(QSize(GRID_SIZE.width(), GRID_SIZE.height()))
        self.list_view.setSpacing(0)
        self.list_view.setMouseTracking(True)
        self.list_view.setSelectionMode(QListView.SelectionMode.SingleSelection)

        root.addWidget(self.list_view, 1)

    def _build_bottom_bar(self, root: QVBoxLayout) -> None:
        bottom = QHBoxLayout()
        bottom.setContentsMargins(0, 0, 0, 0)

        self.empty_label = QLabel("")
        self.empty_label.setObjectName("status_label")
        bottom.addWidget(self.empty_label)

        bottom.addStretch()

        close_button = QPushButton("Закрыть")
        close_button.setObjectName("close_button")
        close_button.clicked.connect(self.close)
        bottom.addWidget(close_button)

        root.addLayout(bottom)

    def set_position(self, pos: int) -> None:
        self.current_pos = pos
        self.apply_current_filters()

    def on_sets_filter_enabled_changed(self, checked: bool) -> None:
        self.sets_filter_enabled = checked
        self.sets_filter_switch.setText("ON" if checked else "OFF")
        self.apply_current_filters()

    def show_sets_popup(self) -> None:
        if self._sets_popup is None:
            self._sets_popup = SetsFilterPopup(
                game_sets=self.store.game_set_options,
                custom_sets=self.store.custom_set_options,
                selected_game_set_ids=self.selected_game_set_ids,
                selected_custom_set_ids=self.selected_custom_set_ids,
                on_selection_changed=self.on_sets_selection_changed,
                parent=self,
            )

        button_pos = self.sets_button.mapToGlobal(QPoint(0, self.sets_button.height() + 4))
        self._sets_popup.move(button_pos)
        self._sets_popup.show()
        self._sets_popup.raise_()
        self._sets_popup.activateWindow()

    def on_sets_selection_changed(
        self,
        selected_game_set_ids: set[int | None],
        selected_custom_set_ids: set[int],
    ) -> None:
        self.selected_game_set_ids = set(selected_game_set_ids)
        self.selected_custom_set_ids = set(selected_custom_set_ids)
        self.update_sets_button_text()
        self.apply_current_filters()

    def update_sets_button_text(self) -> None:
        count = len(self.selected_game_set_ids) + len(self.selected_custom_set_ids)
        self.sets_button.setText(f"Наборы: {count}" if count else "Наборы")

    def apply_current_filters(self) -> None:
        if not self.store.database_exists:
            self.model.set_artifact_ids([])
            self.status_label.setText("База артефактов не найдена")
            self.empty_label.setText("Сначала импортируйте данные из HoYoLAB.")
            return

        base_ids = self.store.ids_for_position(self.current_pos)
        visible_ids = list(base_ids)

        selected_any_sets = bool(self.selected_game_set_ids or self.selected_custom_set_ids)

        if self.sets_filter_enabled and selected_any_sets:
            allowed_ids: set[int] = set()
            allowed_ids.update(self.store.ids_for_game_sets(self.selected_game_set_ids))
            allowed_ids.update(self.store.ids_for_custom_sets(self.selected_custom_set_ids))
            visible_ids = [
                artifact_id
                for artifact_id in base_ids
                if artifact_id in allowed_ids
            ]

        self.model.set_artifact_ids(visible_ids)
        self.update_status(len(visible_ids), len(base_ids))

    def update_status(self, visible_count: int, total_count: int) -> None:
        slot_name = ARTIFACT_POSITIONS[self.current_pos]
        self.status_label.setText(f"{slot_name}: {visible_count}/{total_count}")

        if total_count == 0:
            self.empty_label.setText("Артефакты не найдены.")
        elif visible_count == 0:
            self.empty_label.setText("Нет артефактов по выбранным наборам.")
        else:
            self.empty_label.setText("")

    def reload_from_database(self) -> None:
        self.store = ArtifactBrowserStore.load_from_db()
        self.model.set_store(self.store)
        self._sets_popup = None
        self.selected_game_set_ids.clear()
        self.selected_custom_set_ids.clear()
        self.update_sets_button_text()
        self.apply_current_filters()