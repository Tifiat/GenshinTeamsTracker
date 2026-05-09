from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, QSize
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListView,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtGui import QIcon

from hoyolab_export.paths import PROJECT_ROOT
from .list_model import ArtifactRoles
from .queries import (
    calculate_build_summary,
    create_custom_set,
    delete_custom_set,
    get_custom_set_artifact_ids,
    get_build_preset,
    list_build_presets,
    replace_custom_set_artifacts,
    save_build_preset,
)
from .card_delegate import ArtifactCardDelegate, GRID_SIZE
from .filter_popup import SetsFilterPopup
from .list_model import ArtifactListModel
from .models import ARTIFACT_POSITIONS
from .store import ArtifactBrowserStore
from .sort_popup import SortStatsPopup
from localization import tr

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
QListView[customEditMode="true"] {
    background: #203861;
    border: 1px solid #4f8ee8;
    border-radius: 8px;
}
QListView::item {
    background: transparent;
}
QPushButton#custom_save_button {
    border-color: #4e9b61;
    background: #24452d;
}
QPushButton#custom_save_button:hover {
    background: #2d5938;
}
QPushButton#custom_cancel_button {
    border-color: #b85b5b;
    background: #4a2529;
}
QPushButton#custom_cancel_button:hover {
    background: #5c2d32;
}
QFrame#build_panel {
    border: 1px solid #2b3039;
    border-radius: 10px;
    background: #1f222a;
}
QLabel#panel_title {
    color: #ffffff;
    font-weight: 700;
    font-size: 14px;
}
QLabel#slot_label {
    color: #dce5f7;
    background: #222630;
    border: 1px solid #343b49;
    border-radius: 6px;
    padding: 5px 7px;
}
"""


ARTIFACT_POSITION_LABEL_KEYS = {
    1: "artifact.position.flower",
    2: "artifact.position.plume",
    3: "artifact.position.sands",
    4: "artifact.position.goblet",
    5: "artifact.position.circlet",
}


class ArtifactBrowserWindow(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowFlag(Qt.Window, True)
        self.setWindowTitle(tr("artifact.browser.title"))
        self.resize(1180, 760)
        self.setStyleSheet(WINDOW_STYLE)

        self.current_pos = 1
        self.store = ArtifactBrowserStore.load_from_db()
        self.model = ArtifactListModel(self.store, self)
        self.delegate = ArtifactCardDelegate(self)

        self.sets_filter_enabled = True
        self.selected_game_set_ids: set[str] = set()
        self.selected_custom_set_ids: set[int] = set()
        self.selected_sort_stat_types: list[int] = []
        self._sort_popup: SortStatsPopup | None = None
        self._sets_popup: SetsFilterPopup | None = None
        self.position_buttons: dict[int, QPushButton] = {}
        self.editing_custom_set_id: int | None = None
        self.editing_custom_set_name: str = ""
        self.editing_custom_artifact_ids: set[int] = set()
        self.editing_custom_dirty = False
        self.build_presets: list[dict] = []
        self.selected_build_id: int | None = None
        self.editing_build_id: int | None = None
        self.editing_build_name: str = ""
        self.editing_build_slots: dict[int, int] = {}
        self.editing_build_dirty = False
        self.build_slot_labels: dict[int, QLabel] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        self._build_top_bar(root)
        content = QHBoxLayout()
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(8)
        self._build_list_view(content)
        self._build_build_panel(content)
        root.addLayout(content, 1)
        self._build_bottom_bar(root)

        self.load_build_presets()
        self.apply_current_filters()
        self.update_custom_edit_bar()
        self.update_build_panel()

    def _build_top_bar(self, root: QVBoxLayout) -> None:
        top_frame = QFrame()
        top_frame.setObjectName("top_bar")

        top = QHBoxLayout(top_frame)
        top.setContentsMargins(8, 8, 8, 8)
        top.setSpacing(6)

        self.slot_group = QButtonGroup(self)
        self.slot_group.setExclusive(True)

        for pos in ARTIFACT_POSITIONS:
            button = QPushButton(self._position_label(pos))
            button.setCheckable(True)
            button.clicked.connect(lambda _checked=False, value=pos: self.set_position(value))
            self.slot_group.addButton(button, pos)
            self.position_buttons[pos] = button
            top.addWidget(button)

            if pos == 1:
                button.setChecked(True)

        top.addStretch()

        self.sets_filter_switch = QPushButton()
        self.sets_filter_switch.setObjectName("filter_switch")
        self.sets_filter_switch.setCheckable(True)
        self.sets_filter_switch.setChecked(True)
        self.update_sets_filter_switch_text()
        self.sets_filter_switch.clicked.connect(self.on_sets_filter_enabled_changed)
        top.addWidget(self.sets_filter_switch)

        self.sets_button = QPushButton(tr("artifact.sets.button"))
        self.sort_button = QPushButton(tr("artifact.sort.button"))
        self.sort_button.clicked.connect(self.show_sort_popup)
        top.addWidget(self.sort_button)
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
        self.list_view.setProperty("customEditMode", False)
        self.list_view.setSelectionMode(QListView.SelectionMode.NoSelection)
        self.list_view.clicked.connect(self.on_artifact_clicked)


        root.addWidget(self.list_view, 1)

    def _build_build_panel(self, root: QHBoxLayout) -> None:
        panel = QFrame()
        panel.setObjectName("build_panel")
        panel.setFixedWidth(320)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        self.build_title_label = QLabel(tr("artifact.build.presets_title"))
        self.build_title_label.setObjectName("panel_title")
        layout.addWidget(self.build_title_label)

        self.new_build_button = QPushButton(tr("artifact.build.new"))
        self.new_build_button.clicked.connect(self.start_new_build_preset)
        layout.addWidget(self.new_build_button)

        self.build_preset_list_layout = QVBoxLayout()
        self.build_preset_list_layout.setContentsMargins(0, 0, 0, 0)
        self.build_preset_list_layout.setSpacing(5)
        layout.addLayout(self.build_preset_list_layout)

        self.build_edit_status_label = QLabel("")
        self.build_edit_status_label.setObjectName("status_label")
        self.build_edit_status_label.setWordWrap(True)
        layout.addWidget(self.build_edit_status_label)

        for pos in ARTIFACT_POSITIONS:
            label = QLabel("")
            label.setObjectName("slot_label")
            label.setWordWrap(True)
            self.build_slot_labels[pos] = label
            layout.addWidget(label)

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        self.save_build_button = QPushButton(tr("artifact.build.save"))
        self.save_build_button.setObjectName("custom_save_button")
        self.save_build_button.clicked.connect(self.save_build_preset_edit)
        actions.addWidget(self.save_build_button)

        self.cancel_build_button = QPushButton(tr("artifact.build.cancel"))
        self.cancel_build_button.setObjectName("custom_cancel_button")
        self.cancel_build_button.clicked.connect(self.cancel_build_preset_edit)
        actions.addWidget(self.cancel_build_button)
        layout.addLayout(actions)

        self.build_summary_label = QLabel("")
        self.build_summary_label.setObjectName("status_label")
        self.build_summary_label.setWordWrap(True)
        layout.addWidget(self.build_summary_label, 1)

        root.addWidget(panel)

    def _build_bottom_bar(self, root: QVBoxLayout) -> None:
        bottom = QHBoxLayout()
        bottom.setContentsMargins(0, 0, 0, 0)

        self.empty_label = QLabel("")
        self.empty_label.setObjectName("status_label")

        self.edit_mode_label = QLabel("")
        self.edit_mode_label.setObjectName("status_label")
        bottom.addWidget(self.edit_mode_label)

        self.save_custom_set_button = QPushButton()
        self.save_custom_set_button.setObjectName("custom_save_button")
        self.save_custom_set_button.setIcon(self._ui_icon("save"))
        self.save_custom_set_button.setToolTip(tr("artifact.custom.save"))
        self.save_custom_set_button.clicked.connect(self.save_custom_set_edit)
        bottom.addWidget(self.save_custom_set_button)

        self.cancel_custom_set_button = QPushButton()
        self.cancel_custom_set_button.setObjectName("custom_cancel_button")
        self.cancel_custom_set_button.setIcon(self._ui_icon("x"))
        self.cancel_custom_set_button.setToolTip(tr("artifact.custom.cancel"))
        self.cancel_custom_set_button.clicked.connect(self.cancel_custom_set_edit)
        bottom.addWidget(self.cancel_custom_set_button)

        bottom.addWidget(self.empty_label)

        bottom.addStretch()

        self.close_button = QPushButton(tr("common.close"))
        self.close_button.setObjectName("close_button")
        self.close_button.clicked.connect(self.close)
        bottom.addWidget(self.close_button)

        root.addLayout(bottom)

    def _position_label(self, pos: int) -> str:
        label_key = ARTIFACT_POSITION_LABEL_KEYS.get(pos)
        return tr(label_key) if label_key else str(pos)

    def _ui_icon(self, name: str) -> QIcon:
        return QIcon(str(PROJECT_ROOT / "assets" / "ui" / "icons" / f"{name}.svg"))

    def retranslate_ui(self) -> None:
        self.setWindowTitle(tr("artifact.browser.title"))

        for pos, button in self.position_buttons.items():
            button.setText(self._position_label(pos))

        self.close_button.setText(tr("common.close"))
        self.save_custom_set_button.setToolTip(tr("artifact.custom.save"))
        self.cancel_custom_set_button.setToolTip(tr("artifact.custom.cancel"))
        self.build_title_label.setText(tr("artifact.build.presets_title"))
        self.new_build_button.setText(tr("artifact.build.new"))
        self.save_build_button.setText(tr("artifact.build.save"))
        self.cancel_build_button.setText(tr("artifact.build.cancel"))
        self.update_sets_filter_switch_text()
        self.update_sets_button_text()
        self.update_sort_button_text()
        self.refresh_build_preset_list()
        self.update_build_panel()
        self.apply_current_filters()

    def set_position(self, pos: int) -> None:
        self.current_pos = pos
        self.apply_current_filters()

    def on_sets_filter_enabled_changed(self, checked: bool) -> None:
        self.sets_filter_enabled = checked
        self.update_sets_filter_switch_text()
        self.apply_current_filters()

    def show_sets_popup(self) -> None:
        if self._sets_popup is None:
            self._sets_popup = SetsFilterPopup(
                game_sets=self.store.game_set_options,
                custom_sets=self.store.custom_set_options,
                selected_game_set_ids=self.selected_game_set_ids,
                selected_custom_set_ids=self.selected_custom_set_ids,
                on_selection_changed=self.on_sets_selection_changed,
                on_custom_set_create=self.create_and_edit_custom_set,
                on_custom_set_edit=self.start_custom_set_edit,
                on_custom_set_delete=self.delete_custom_set_from_popup,
                parent=self,
            )

        button_pos = self.sets_button.mapToGlobal(QPoint(0, self.sets_button.height() + 4))
        self._move_popup_inside_screen(self._sets_popup, button_pos)
        self._sets_popup.show()
        self._sets_popup.raise_()
        self._sets_popup.activateWindow()

    def show_sort_popup(self) -> None:
        if self._sort_popup is None:
            self._sort_popup = SortStatsPopup(
                selected_stat_types=self.selected_sort_stat_types,
                on_selection_changed=self.on_sort_selection_changed,
                parent=self,
            )

        button_pos = self.sort_button.mapToGlobal(QPoint(0, self.sort_button.height() + 4))
        self._move_popup_inside_screen(self._sort_popup, button_pos)
        self._sort_popup.show()
        self._sort_popup.raise_()
        self._sort_popup.activateWindow()

    def _move_popup_inside_screen(self, popup: QWidget, preferred_pos: QPoint) -> None:
        popup_size = popup.sizeHint().expandedTo(popup.minimumSize())
        popup.resize(popup_size)

        screen = self.sets_button.screen() or self.screen() or QApplication.primaryScreen()
        if screen is None:
            popup.move(preferred_pos)
            return

        available = screen.availableGeometry()

        x = preferred_pos.x()
        y = preferred_pos.y()

        max_x = available.x() + available.width() - popup_size.width()
        max_y = available.y() + available.height() - popup_size.height()

        if x > max_x:
            x = max_x
        if x < available.x():
            x = available.x()

        if y > max_y:
            above_pos = self.sets_button.mapToGlobal(
                QPoint(0, -popup_size.height() - 4)
            )
            y = above_pos.y() if above_pos.y() >= available.y() else max_y

        if y < available.y():
            y = available.y()

        popup.move(QPoint(x, y))

    def on_sets_selection_changed(
        self,
        selected_game_set_ids: set[str],
        selected_custom_set_ids: set[int],
    ) -> None:
        self.selected_game_set_ids = set(selected_game_set_ids)
        self.selected_custom_set_ids = set(selected_custom_set_ids)
        self.update_sets_button_text()
        self.apply_current_filters()

    def on_sort_selection_changed(self, selected_stat_types: list[int]) -> None:
        self.selected_sort_stat_types = list(selected_stat_types[:4])
        self.update_sort_button_text()
        self.apply_current_filters()

    def update_sort_button_text(self) -> None:
        count = len(self.selected_sort_stat_types)
        self.sort_button.setText(
            tr("artifact.sort.button_count", count=count)
            if count
            else tr("artifact.sort.button")
        )

    def update_sets_button_text(self) -> None:
        count = len(self.selected_game_set_ids) + len(self.selected_custom_set_ids)
        self.sets_button.setText(
            tr("artifact.sets.button_count", count=count)
            if count
            else tr("artifact.sets.button")
        )

    def update_sets_filter_switch_text(self) -> None:
        self.sets_filter_switch.setText(
            tr("artifact.sets.filter_on")
            if self.sets_filter_enabled
            else tr("artifact.sets.filter_off")
        )

    def apply_current_filters(self) -> None:
        if not self.store.database_exists:
            self.model.set_artifact_ids([])
            self.status_label.setText(tr("artifact.browser.database_missing"))
            self.empty_label.setText(tr("artifact.browser.import_first"))
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

        visible_ids = self.store.sort_artifact_ids(
            visible_ids,
            self.selected_sort_stat_types,
        )
        self.model.set_artifact_ids(visible_ids)
        self.update_status(len(visible_ids), len(base_ids))

    def update_status(self, visible_count: int, total_count: int) -> None:
        slot_name = self._position_label(self.current_pos)
        self.status_label.setText(f"{slot_name}: {visible_count}/{total_count}")

        if total_count == 0:
            self.empty_label.setText(tr("artifact.browser.empty"))
        elif visible_count == 0:
            self.empty_label.setText(tr("artifact.browser.empty_for_sets"))
        else:
            self.empty_label.setText("")

    def reload_from_database(
        self,
        *,
        keep_custom_edit: bool = False,
        reset_filters: bool = True,
        reset_sort: bool = True,
        reset_popup: bool = True,
        confirm_custom_edit: bool = True,
    ) -> None:
        if confirm_custom_edit and not keep_custom_edit:
            if not self.confirm_discard_custom_edit():
                return

        self.store = ArtifactBrowserStore.load_from_db()
        self.model.set_store(self.store)
        if not keep_custom_edit:
            self.finish_custom_set_edit()
        if reset_popup:
            if self._sets_popup is not None:
                self._sets_popup.close()
            self._sets_popup = None
        if reset_filters:
            self.selected_game_set_ids.clear()
            self.selected_custom_set_ids.clear()
        self.update_sets_button_text()
        self.apply_current_filters()
        if reset_sort:
            self._sort_popup = None
            self.selected_sort_stat_types.clear()
            self.update_sort_button_text()
        self.load_build_presets()
        self.update_custom_edit_bar()
        self.update_build_panel()

    def on_artifact_clicked(self, index) -> None:
        artifact = index.data(ArtifactRoles.ArtifactRole)
        if artifact is None:
            return

        if self.editing_custom_set_id is not None:
            self.toggle_custom_set_artifact(artifact.id)
            return

        if self.editing_build_id is not None or self.editing_build_name:
            self.assign_build_artifact(artifact.id)

    def toggle_custom_set_artifact(self, artifact_id: int) -> None:
        if artifact_id in self.editing_custom_artifact_ids:
            self.editing_custom_artifact_ids.remove(artifact_id)
        else:
            self.editing_custom_artifact_ids.add(artifact_id)

        self.editing_custom_dirty = True
        self.delegate.set_custom_edit_artifact_ids(self.editing_custom_artifact_ids)
        self.update_custom_edit_bar()
        self.list_view.viewport().update()

    def create_and_edit_custom_set(self, name: str) -> None:
        name = name.strip()
        if not name:
            self.empty_label.setText(tr("artifact.custom.empty_name"))
            return

        if not self.confirm_discard_custom_edit():
            return

        tag_id = create_custom_set(name)
        if self._sets_popup is not None:
            self._sets_popup.close()
            self._sets_popup = None
        self.reload_from_database(
            keep_custom_edit=False,
            reset_filters=False,
            reset_sort=False,
            confirm_custom_edit=False,
        )
        self.start_custom_set_edit(tag_id)
        self._sets_popup = None

    def start_custom_set_edit(self, tag_id: int) -> None:
        if tag_id != self.editing_custom_set_id:
            if not self.confirm_discard_custom_edit():
                return

        option = next(
            (
                option
                for option in self.store.custom_set_options
                if option.tag_id == tag_id
            ),
            None,
        )

        self.editing_custom_set_id = int(tag_id)
        self.editing_custom_set_name = option.name if option else str(tag_id)
        self.editing_custom_artifact_ids = get_custom_set_artifact_ids(tag_id)
        self.editing_custom_dirty = False

        if tag_id in self.selected_custom_set_ids:
            self.selected_custom_set_ids.remove(tag_id)
            self.update_sets_button_text()
            self.apply_current_filters()

        self.delegate.set_custom_edit_artifact_ids(self.editing_custom_artifact_ids)
        self.update_custom_edit_bar()
        self.list_view.viewport().update()

        if self._sets_popup is not None:
            self._sets_popup.close()
            self._sets_popup = None

    def _clear_layout(self, layout: QVBoxLayout | QHBoxLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            child_layout = item.layout()
            if widget is not None:
                widget.deleteLater()
            if child_layout is not None:
                self._clear_layout(child_layout)

    def load_build_presets(self) -> None:
        self.build_presets = list_build_presets()
        self.refresh_build_preset_list()

    def refresh_build_preset_list(self) -> None:
        self._clear_layout(self.build_preset_list_layout)

        if not self.build_presets:
            empty_label = QLabel(tr("artifact.build.empty_presets"))
            empty_label.setObjectName("status_label")
            empty_label.setWordWrap(True)
            self.build_preset_list_layout.addWidget(empty_label)
            return

        for preset in self.build_presets:
            button = QPushButton(
                tr(
                    "artifact.build.preset_row",
                    name=preset["name"],
                    count=preset["slot_count"],
                )
            )
            button.setCheckable(True)
            button.setChecked(preset["id"] == self.selected_build_id)
            button.clicked.connect(
                lambda _checked=False, build_id=preset["id"]: self.start_build_preset_edit(build_id)
            )
            self.build_preset_list_layout.addWidget(button)

    def start_new_build_preset(self) -> None:
        self.selected_build_id = None
        self.editing_build_id = None
        self.editing_build_name = tr("artifact.build.new_default_name")
        self.editing_build_slots = {}
        self.editing_build_dirty = False
        self.update_build_panel()
        self.refresh_build_preset_list()

    def start_build_preset_edit(self, build_id: int) -> None:
        preset = get_build_preset(build_id)
        if preset is None:
            return

        self.selected_build_id = int(build_id)
        self.editing_build_id = int(build_id)
        self.editing_build_name = preset["name"]
        self.editing_build_slots = {
            int(slot["pos"]): int(slot["artifact_id"])
            for slot in preset.get("slots", [])
        }
        self.editing_build_dirty = False
        self.update_build_panel()
        self.refresh_build_preset_list()

    def assign_build_artifact(self, artifact_id: int) -> None:
        try:
            artifact = self.store.artifact(artifact_id)
        except KeyError:
            return

        self.editing_build_slots[int(artifact.pos)] = int(artifact.id)
        self.editing_build_dirty = True
        self.update_build_panel()

    def save_build_preset_edit(self) -> None:
        if not self.editing_build_name:
            return

        build_id = save_build_preset(
            build_id=self.editing_build_id,
            name=self.editing_build_name,
            slots=self.editing_build_slots,
        )
        self.selected_build_id = build_id
        self.editing_build_id = build_id
        self.editing_build_dirty = False
        self.load_build_presets()
        self.update_build_panel()

    def cancel_build_preset_edit(self) -> None:
        self.finish_build_preset_edit()

    def finish_build_preset_edit(self) -> None:
        self.editing_build_id = None
        self.editing_build_name = ""
        self.editing_build_slots = {}
        self.editing_build_dirty = False
        self.update_build_panel()
        self.refresh_build_preset_list()

    def update_build_panel(self) -> None:
        editing = bool(self.editing_build_name)

        self.build_edit_status_label.setText(
            tr("artifact.build.editing_status", name=self.editing_build_name)
            if editing
            else tr("artifact.build.no_selection")
        )
        self.save_build_button.setVisible(editing)
        self.cancel_build_button.setVisible(editing)

        for pos, label in self.build_slot_labels.items():
            artifact_id = self.editing_build_slots.get(pos) if editing else None
            label.setText(self._build_slot_text(pos, artifact_id))

        self.build_summary_label.setText(self._build_summary_text())

    def _build_slot_text(self, pos: int, artifact_id: int | None) -> str:
        slot_name = self._position_label(pos)
        if artifact_id is None:
            return f"{slot_name}: {tr('artifact.build.slot_empty')}"

        try:
            artifact = self.store.artifact(artifact_id)
        except KeyError:
            return f"{slot_name}: {tr('artifact.build.slot_missing')}"

        return (
            f"{slot_name}: {artifact.name}\n"
            f"{artifact.main_property_name} {artifact.main_property_value}"
        )

    def _build_summary_text(self) -> str:
        if not self.editing_build_name:
            return tr("artifact.build.summary_empty")

        try:
            if self.editing_build_id is not None and not self.editing_build_dirty:
                summary = calculate_build_summary(build_id=self.editing_build_id)
            else:
                summary = calculate_build_summary(slots=self.editing_build_slots)
        except Exception as exc:
            return tr("artifact.build.summary_error", error=str(exc))

        if not summary:
            return tr("artifact.build.summary_empty")

        lines = [tr("artifact.build.summary_title")]
        if summary["missing_positions"]:
            missing = ", ".join(
                self._position_label(pos)
                for pos in summary["missing_positions"]
            )
            lines.append(tr("artifact.build.summary_missing", positions=missing))

        set_counts = summary.get("set_counts") or []
        if set_counts:
            sets_text = ", ".join(
                f"{item['set_name'] or item['set_uid']} x{item['count']}"
                for item in set_counts
            )
            lines.append(tr("artifact.build.summary_sets", sets=sets_text))

        lines.append(
            tr(
                "artifact.build.summary_cv",
                cv=summary.get("crit_value", 0),
                procs=summary.get("proc_count", 0),
            )
        )

        stats = summary.get("total_stats") or []
        if stats:
            stat_lines = [
                f"{item['property_name']}: {item['raw_value']}"
                for item in stats[:8]
            ]
            lines.append(tr("artifact.build.summary_stats", stats=", ".join(stat_lines)))

        return "\n".join(lines)

    def save_custom_set_edit(self) -> None:
        self._save_custom_set_edit(reload_after=True)

    def _save_custom_set_edit(self, *, reload_after: bool) -> None:
        if self.editing_custom_set_id is None:
            return

        replace_custom_set_artifacts(
            self.editing_custom_set_id,
            self.editing_custom_artifact_ids,
        )
        self.finish_custom_set_edit()
        if not reload_after:
            return

        self.reload_from_database(
            keep_custom_edit=False,
            reset_filters=False,
            reset_sort=False,
            confirm_custom_edit=False,
        )

    def cancel_custom_set_edit(self) -> None:
        self.finish_custom_set_edit()

    def delete_custom_set_from_popup(self, tag_id: int):
        if not self.confirm_discard_custom_edit():
            return self.store.custom_set_options

        delete_custom_set(tag_id)

        if self.editing_custom_set_id == tag_id:
            self.finish_custom_set_edit()

        self.selected_custom_set_ids.discard(tag_id)
        self.reload_from_database(
            keep_custom_edit=False,
            reset_filters=False,
            reset_sort=False,
            reset_popup=False,
            confirm_custom_edit=False,
        )
        self.update_sets_button_text()
        self.apply_current_filters()
        return self.store.custom_set_options

    def confirm_discard_custom_edit(self) -> bool:
        if not self.editing_custom_dirty:
            return True

        box = QMessageBox(self)
        box.setWindowTitle(tr("artifact.custom.unsaved_title"))
        box.setIcon(QMessageBox.Icon.Warning)
        box.setText(
            tr(
                "artifact.custom.unsaved_message",
                name=self.editing_custom_set_name,
            )
        )

        save_button = box.addButton(
            tr("artifact.custom.unsaved_save"),
            QMessageBox.ButtonRole.AcceptRole,
        )
        discard_button = box.addButton(
            tr("artifact.custom.unsaved_discard"),
            QMessageBox.ButtonRole.DestructiveRole,
        )
        cancel_button = box.addButton(
            tr("artifact.custom.unsaved_cancel"),
            QMessageBox.ButtonRole.RejectRole,
        )
        box.setDefaultButton(save_button)
        box.exec()

        clicked_button = box.clickedButton()
        if clicked_button == save_button:
            self._save_custom_set_edit(reload_after=True)
            return True
        if clicked_button == discard_button:
            self.finish_custom_set_edit()
            return True
        if clicked_button == cancel_button:
            return False
        return False

    def closeEvent(self, event) -> None:
        if self.confirm_discard_custom_edit():
            event.accept()
        else:
            event.ignore()

    def finish_custom_set_edit(self) -> None:
        self.editing_custom_set_id = None
        self.editing_custom_set_name = ""
        self.editing_custom_artifact_ids.clear()
        self.editing_custom_dirty = False

        self.delegate.set_custom_edit_artifact_ids(set())
        self.update_custom_edit_bar()
        self.list_view.viewport().update()

    def update_custom_edit_bar(self) -> None:
        editing = self.editing_custom_set_id is not None

        self.edit_mode_label.setVisible(editing)
        self.save_custom_set_button.setVisible(editing)
        self.cancel_custom_set_button.setVisible(editing)
        self.list_view.setProperty("customEditMode", editing)
        self.list_view.style().unpolish(self.list_view)
        self.list_view.style().polish(self.list_view)

        if not editing:
            self.edit_mode_label.setText("")
            return

        self.edit_mode_label.setText(
            tr(
                "artifact.custom.editing_status",
                name=self.editing_custom_set_name,
                count=len(self.editing_custom_artifact_ids),
            )
        )
