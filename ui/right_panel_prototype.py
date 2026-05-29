from __future__ import annotations

import html
import re
from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QEvent, QSize, Qt, Signal
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QStyle,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from run_workspace.right_panel_prototype_view_model import (
    MODE_ABYSS,
    MODE_DPS_DUMMY,
    RightPanelBonusSourceDisplayItem,
    RightPanelBuildMiniSetViewModel,
    RightPanelChamberRowViewModel,
    RightPanelDetailRowViewModel,
    RightPanelGcsimStatusViewModel,
    RightPanelPrototypeViewModel,
    RightPanelSelectedDetailsViewModel,
    RightPanelSlotPrototypeViewModel,
    RightPanelTeamPrototypeViewModel,
)
from ui.utils.pixmap_utils import (
    draw_count_badge,
    make_diagonal_split_pixmap,
    scale_trimmed_pixmap_to_size,
)
from run_workspace.perf import log_perf, perf_ms, perf_now
from ui.utils.horizontal_scroll import HorizontalDragScrollArea
from ui.utils.overlay_scroll import OverlayVerticalScrollArea
from ui.utils.tooltips import install_custom_tooltip
from ui.artifact_browser.queries import list_set_bonus_description_map


RIGHT_PANEL_PROTOTYPE_MIN_WIDTH = 660
RIGHT_PANEL_PROTOTYPE_CONTENT_MIN_WIDTH = 640
SLOT_CARD_MARGIN = 5
SLOT_PORTRAIT_SIZE = 96
SLOT_EQUIP_BOX_SIZE = 46
SLOT_EQUIP_ICON_SIZE = 42
SLOT_WEAPON_ICON_SIZE = 52
SLOT_BUILD_BONUS_FEATHER = 3
SLOT_TOP_SPACING = 2
SLOT_CLUSTER_WIDTH = SLOT_PORTRAIT_SIZE + SLOT_TOP_SPACING + SLOT_EQUIP_BOX_SIZE
SLOT_BADGE_HEIGHT = 22
SLOT_WARNING_BADGE_WIDTH = SLOT_EQUIP_BOX_SIZE
SLOT_CARD_WIDTH = SLOT_CLUSTER_WIDTH + SLOT_CARD_MARGIN * 2
SLOT_CARD_FIXED_HEIGHT = 154
SLOT_NAME_HEIGHT = 18

_FIT_PIXMAP_CACHE: dict[tuple[str, int, int], QPixmap | None] = {}
_BUILD_MINI_SET_ICON_PIXMAP_CACHE: dict[
    tuple[str, int, int, int, int],
    QPixmap | None,
] = {}
_BONUS_SOURCE_ICON_PIXMAP_CACHE: dict[
    tuple[str, int, int, int, int],
    QPixmap | None,
] = {}
_BONUS_MEMBER_SIDE_ICON_PIXMAP_CACHE: dict[
    tuple[str, int, int, int, int, int, int],
    QPixmap | None,
] = {}
BONUS_MEMBER_ICON_SCALE = 125
BONUS_MEMBER_ICON_BOTTOM_PADDING = 0
_PROJECT_ROOT = Path(__file__).resolve().parents[1]


class RightPanelPrototypeWidget(QWidget):
    """Standalone visual prototype for the future right panel."""

    mode_requested = Signal(str)
    slot_selected = Signal(int, int)
    external_bonuses_toggled = Signal(bool)

    def __init__(
        self,
        model: RightPanelPrototypeViewModel,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setObjectName("RightPanelPrototypeWidget")
        self.setMinimumWidth(RIGHT_PANEL_PROTOTYPE_MIN_WIDTH)
        self._model = model
        self._team_widgets: list[RightPanelTeamPrototypeWidget] = []
        self._slot_widgets: list[RightPanelSlotPrototypeWidget] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._scroll = OverlayVerticalScrollArea(auto_hide_ms=850)
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        root.addWidget(self._scroll)

        self._content = QWidget()
        self._content.setObjectName("RightPanelPrototypeContent")
        self._content.setMinimumWidth(RIGHT_PANEL_PROTOTYPE_CONTENT_MIN_WIDTH)
        self._layout = QVBoxLayout(self._content)
        self._layout.setContentsMargins(8, 8, 8, 8)
        self._layout.setSpacing(7)
        self._scroll.setWidget(self._content)

        self._tab_group = QButtonGroup(self)
        self._tab_group.setExclusive(True)
        self._tabs_container = QWidget()
        self._tabs_layout = QHBoxLayout(self._tabs_container)
        self._tabs_layout.setContentsMargins(0, 0, 0, 0)
        self._tabs_layout.setSpacing(6)
        self._layout.addWidget(self._tabs_container)
        self._create_tabs(model)

        self._teams_container = QWidget()
        self._teams_layout = QVBoxLayout(self._teams_container)
        self._teams_layout.setContentsMargins(0, 0, 0, 0)
        self._teams_layout.setSpacing(6)
        self._layout.addWidget(self._teams_container)

        self._chamber_table = ChamberTableBlockWidget()
        self._layout.addWidget(self._chamber_table)

        self._details_frame = SelectedCharacterDetailsWidget()
        self._details_frame.external_bonuses_toggled.connect(
            self.external_bonuses_toggled.emit
        )
        self._layout.addWidget(self._details_frame)

        self._actions = ActionBarPrototypeWidget(model.action_labels)
        self._layout.addWidget(self._actions)
        self._layout.addStretch(1)

        self.setStyleSheet(_stylesheet())
        self.set_model(model)

    def set_model(self, model: RightPanelPrototypeViewModel) -> None:
        total_start = perf_now()
        QToolTip.hideText()
        self._model = model
        tabs_start = perf_now()
        self._sync_tabs(model.mode)
        tabs_ms = perf_ms(tabs_start)
        teams_start = perf_now()
        teams_mode = "in_place"
        if self._teams_structure_matches(model):
            for team_widget, team in zip(self._team_widgets, model.teams):
                team_widget.set_model(team)
        else:
            teams_mode = "rebuild"
            self._rebuild_team_widgets(model)
        self._slot_widgets = [
            slot_widget
            for team_widget in self._team_widgets
            for slot_widget in team_widget.slot_widgets()
        ]
        self._sync_teams_container_fixed_height()
        teams_ms = perf_ms(teams_start)

        chamber_start = perf_now()
        self._chamber_table.set_rows(
            model.chamber_headers,
            model.chamber_rows,
            total_seconds=model.total_seconds,
            gcsim_status=model.gcsim_status,
        )
        chamber_ms = perf_ms(chamber_start)
        details_start = perf_now()
        self._details_frame.set_details(model.selected_details)
        details_ms = perf_ms(details_start)
        actions_start = perf_now()
        self._actions.set_labels(model.action_labels)
        actions_ms = perf_ms(actions_start)
        self._settle_content_layout()
        log_perf(
            "right_panel_set_model_widget",
            total=perf_ms(total_start),
            tabs=tabs_ms,
            teams=teams_ms,
            teams_mode=teams_mode,
            chamber=chamber_ms,
            details=details_ms,
            actions=actions_ms,
        )

    def recommended_standalone_size(self) -> QSize:
        self._content.adjustSize()
        hint = self._content.sizeHint()
        return QSize(
            max(RIGHT_PANEL_PROTOTYPE_MIN_WIDTH, hint.width()),
            max(1, hint.height() + self._scroll.frameWidth() * 2),
        )

    def _create_tabs(self, model: RightPanelPrototypeViewModel) -> None:
        for label in model.mode_tabs:
            button = QPushButton(label)
            button.setCheckable(True)
            button.setObjectName("ModeTabButton")
            mode = MODE_DPS_DUMMY if "DPS" in label else MODE_ABYSS
            button.clicked.connect(
                lambda _checked=False, value=mode: self.mode_requested.emit(value)
            )
            self._tab_group.addButton(button)
            self._tabs_layout.addWidget(button)

    def _sync_tabs(self, mode: str) -> None:
        for button in self._tab_group.buttons():
            should_check = (
                (mode == MODE_DPS_DUMMY and "DPS" in button.text())
                or (mode == MODE_ABYSS and "Abyss" in button.text())
            )
            button.setChecked(should_check)

    def _clear_layout(self, layout: QVBoxLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _teams_structure_matches(self, model: RightPanelPrototypeViewModel) -> bool:
        if len(self._team_widgets) != len(model.teams):
            return False
        return all(
            team_widget.slot_count() == len(team.slots)
            for team_widget, team in zip(self._team_widgets, model.teams)
        )

    def _rebuild_team_widgets(self, model: RightPanelPrototypeViewModel) -> None:
        self._clear_layout(self._teams_layout)
        self._team_widgets.clear()
        self._slot_widgets.clear()

        for team in model.teams:
            team_widget = RightPanelTeamPrototypeWidget(team)
            team_widget.slot_selected.connect(self.slot_selected.emit)
            self._team_widgets.append(team_widget)
            self._slot_widgets.extend(team_widget.slot_widgets())
            self._teams_layout.addWidget(team_widget)

    def _sync_teams_container_fixed_height(self) -> None:
        if not self._team_widgets:
            self._teams_container.setMinimumHeight(0)
            self._teams_container.setMaximumHeight(16777215)
            return
        spacing = max(0, self._teams_layout.spacing())
        height = sum(team.minimumHeight() for team in self._team_widgets)
        height += max(0, len(self._team_widgets) - 1) * spacing
        self._teams_container.setFixedHeight(height)


    def _settle_content_layout(self) -> None:
        self._teams_layout.activate()
        self._layout.invalidate()
        self._layout.activate()

class RightPanelTeamPrototypeWidget(QFrame):
    slot_selected = Signal(int, int)

    def __init__(
        self,
        model: RightPanelTeamPrototypeViewModel,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setObjectName("TeamSlotRow")
        self._model = model
        self._slot_widgets: list[RightPanelSlotPrototypeWidget] = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(0)

        self._grid_container = QWidget()
        self._grid = QGridLayout(self._grid_container)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(4)
        self._grid.setVerticalSpacing(6)
        layout.addWidget(self._grid_container)
        self._rebuild_slot_widgets(model)
        self._sync_fixed_height()

    def set_model(self, model: RightPanelTeamPrototypeViewModel) -> None:
        self._model = model
        if len(model.slots) != len(self._slot_widgets):
            self._rebuild_slot_widgets(model)
            self._sync_fixed_height()
            return
        for slot_widget, slot in zip(self._slot_widgets, model.slots):
            slot_widget.set_model(slot)

    def slot_count(self) -> int:
        return len(self._slot_widgets)

    def slot_widgets(self) -> list["RightPanelSlotPrototypeWidget"]:
        return list(self._slot_widgets)

    def _rebuild_slot_widgets(self, model: RightPanelTeamPrototypeViewModel) -> None:
        _clear_layout(self._grid)
        self._slot_widgets.clear()
        for index, slot in enumerate(model.slots):
            widget = RightPanelSlotPrototypeWidget(slot)
            widget.clicked.connect(self.slot_selected.emit)
            self._slot_widgets.append(widget)
            self._grid.addWidget(widget, index // 4, index % 4)

    def _sync_fixed_height(self) -> None:
        slot_count = max(1, len(self._slot_widgets))
        rows = max(1, (slot_count + 3) // 4)
        vertical_spacing = max(0, self._grid.verticalSpacing())
        grid_height = rows * SLOT_CARD_FIXED_HEIGHT + max(0, rows - 1) * vertical_spacing
        frame_height = grid_height + 8
        self._grid_container.setFixedHeight(grid_height)
        self.setFixedHeight(frame_height)


class RightPanelSlotPrototypeWidget(QFrame):
    clicked = Signal(int, int)

    def __init__(
        self,
        model: RightPanelSlotPrototypeViewModel,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._model = model
        self._model_key: tuple[object, ...] | None = None
        self._weapon_tooltip_controller = None
        self._warning_tooltip_controller = None
        self.setObjectName("SlotCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setFixedWidth(SLOT_CARD_WIDTH)
        self.setFixedHeight(SLOT_CARD_FIXED_HEIGHT)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(
            SLOT_CARD_MARGIN,
            SLOT_CARD_MARGIN,
            SLOT_CARD_MARGIN,
            SLOT_CARD_MARGIN,
        )
        outer.setSpacing(3)

        image_cluster = QWidget()
        image_cluster.setFixedWidth(SLOT_CLUSTER_WIDTH)
        cluster_layout = QVBoxLayout(image_cluster)
        cluster_layout.setContentsMargins(0, 0, 0, 0)
        cluster_layout.setSpacing(4)
        outer.addWidget(image_cluster, alignment=Qt.AlignmentFlag.AlignLeft)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(SLOT_TOP_SPACING)
        cluster_layout.addLayout(top)

        self._portrait = QLabel("")
        self._portrait.setAlignment(Qt.AlignmentFlag.AlignCenter)
        portrait_size = QSize(SLOT_PORTRAIT_SIZE, SLOT_PORTRAIT_SIZE)
        self._portrait.setFixedSize(portrait_size)
        top.addWidget(self._portrait, alignment=Qt.AlignmentFlag.AlignLeft)

        side = QVBoxLayout()
        side.setSpacing(4)
        side.setContentsMargins(0, 0, 0, 0)
        top.addLayout(side)

        self._weapon = QLabel("")
        self._weapon.setObjectName("MiniEquipBox")
        self._weapon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._weapon.setFixedSize(SLOT_EQUIP_BOX_SIZE, SLOT_EQUIP_BOX_SIZE)
        side.addWidget(self._weapon, alignment=Qt.AlignmentFlag.AlignLeft)

        self._artifact = BuildMiniSetStackWidget(model)
        side.addWidget(self._artifact, alignment=Qt.AlignmentFlag.AlignLeft)

        footer = QHBoxLayout()
        footer.setContentsMargins(0, 0, 0, 0)
        footer.setSpacing(4)
        cluster_layout.addLayout(footer)

        self._stat_badge = QLabel("")
        self._stat_badge.setObjectName("StatBadge")
        self._stat_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._stat_badge.setFixedSize(SLOT_PORTRAIT_SIZE, SLOT_BADGE_HEIGHT)
        footer.addWidget(self._stat_badge)
        footer.addSpacing(SLOT_TOP_SPACING)

        self._warning = QLabel("")
        self._warning.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._warning.setFixedSize(SLOT_WARNING_BADGE_WIDTH, SLOT_BADGE_HEIGHT)
        footer.addWidget(self._warning)

        self._name = QLabel("")
        self._name.setObjectName("SlotName")
        self._name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._name.setWordWrap(False)
        self._name.setFixedHeight(SLOT_NAME_HEIGHT)
        outer.addWidget(self._name)
        self.set_model(model)

    def set_model(self, model: RightPanelSlotPrototypeViewModel) -> None:
        model_key = (
            model.team_index,
            model.slot_index,
            model.is_empty,
            model.is_selected,
            model.character_title,
            model.portrait_label,
            model.portrait_path,
            model.weapon_square_label,
            model.weapon_image_path,
            model.weapon_tooltip,
            model.artifact_square_label,
            model.artifact_image_path,
            tuple(model.build_mini_sets),
            model.stat_badge,
            model.warning_count,
            model.warning_tooltip,
        )
        if model_key == self._model_key:
            self._model = model
            return

        self._model_key = model_key
        self._model = model
        _set_object_name(self, "SlotCardSelected" if model.is_selected else "SlotCard")

        _set_object_name(
            self._portrait,
            "PortraitBoxEmpty" if model.is_empty else "PortraitBox",
        )
        self._portrait.clear()
        portrait_pixmap = _fit_pixmap(
            model.portrait_path,
            QSize(SLOT_PORTRAIT_SIZE, SLOT_PORTRAIT_SIZE),
        )
        if portrait_pixmap is not None:
            self._portrait.setPixmap(portrait_pixmap)
        else:
            self._portrait.setText(model.portrait_label)

        self._weapon.clear()
        self._weapon.setText(model.weapon_square_label)
        weapon_pixmap = _fit_pixmap(
            model.weapon_image_path,
            QSize(SLOT_WEAPON_ICON_SIZE, SLOT_WEAPON_ICON_SIZE),
        )
        if weapon_pixmap is not None:
            self._weapon.setPixmap(weapon_pixmap)
        self._weapon_tooltip_controller = _set_custom_tooltip_text(
            self._weapon,
            self._weapon_tooltip_controller,
            model.weapon_tooltip,
        )

        self._artifact.set_model(model)
        self._stat_badge.setText(model.stat_badge)

        if model.warning_count:
            _set_object_name(self._warning, "WarningBadge")
            self._warning.setText(f"!{model.warning_count}")
            self._warning_tooltip_controller = _set_custom_tooltip_text(
                self._warning,
                self._warning_tooltip_controller,
                model.warning_tooltip,
            )
        else:
            _set_object_name(self._warning, "")
            self._warning.setText("")
            self._warning_tooltip_controller = _set_custom_tooltip_text(
                self._warning,
                self._warning_tooltip_controller,
                "",
            )

        self._name.setText(model.character_title)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._model.team_index, self._model.slot_index)
        super().mousePressEvent(event)


class BuildMiniSetStackWidget(QLabel):
    def __init__(
        self,
        model: RightPanelSlotPrototypeViewModel,
        parent: QWidget | None = None,
    ):
        super().__init__("", parent)
        self._tooltip_controller = None
        self._model_key: tuple[object, ...] | None = None
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedSize(SLOT_EQUIP_BOX_SIZE, SLOT_EQUIP_BOX_SIZE)
        self.set_model(model)

    def set_model(self, model: RightPanelSlotPrototypeViewModel) -> None:
        model_key = (
            model.artifact_square_label,
            model.artifact_image_path,
            tuple(model.build_mini_sets),
        )
        if model_key == self._model_key:
            return

        self._model_key = model_key
        is_missing = model.artifact_square_label in {"Equip", "Fix", "ART"}
        _set_object_name(self, "MiniEquipBoxMissing" if is_missing else "MiniEquipBox")
        self.clear()
        self.setText(model.artifact_square_label)

        pixmap = _build_mini_set_stack_pixmap(model.build_mini_sets)
        if pixmap is None and model.artifact_image_path:
            pixmap = _fit_pixmap(
                model.artifact_image_path,
                QSize(SLOT_EQUIP_ICON_SIZE, SLOT_EQUIP_ICON_SIZE),
            )
        if pixmap is not None:
            self.setText("")
            self.setPixmap(pixmap)
        elif model.build_mini_sets:
            self.setText(_build_mini_set_fallback_text(model.build_mini_sets))

        tooltip = _build_mini_set_tooltip_html(model.build_mini_sets)
        self._tooltip_controller = _set_custom_tooltip_text(
            self,
            self._tooltip_controller,
            tooltip,
        )


class ChamberTableBlockWidget(QFrame):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("InfoBlock")
        self._layout = QVBoxLayout(self)
        self._rows_key: tuple[object, ...] | None = None
        self._layout.setContentsMargins(10, 10, 10, 10)
        self._layout.setSpacing(7)

    def set_rows(
        self,
        headers: tuple[str, ...],
        rows: tuple[RightPanelChamberRowViewModel, ...],
        *,
        total_seconds: int,
        gcsim_status: RightPanelGcsimStatusViewModel,
    ) -> None:
        rows_key = (
            tuple(headers),
            tuple(
                (
                    row.chamber_label,
                    row.team1_time,
                    row.team1_seconds,
                    row.team2_time,
                    row.team2_seconds,
                    row.factual_team1,
                    row.factual_team2,
                    row.sim_team1,
                    row.sim_team2,
                    row.total_seconds,
                )
                for row in rows
            ),
            int(total_seconds),
            gcsim_status.status,
            gcsim_status.button_label,
        )
        if rows_key == self._rows_key:
            return
        self._rows_key = rows_key

        _clear_layout(self._layout)

        grid_container = QWidget()
        grid = QGridLayout(grid_container)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(5)
        grid.setVerticalSpacing(5)
        grid.setColumnMinimumWidth(0, 34)
        grid.setColumnStretch(0, 0)
        for column in range(1, 7):
            grid.setColumnStretch(column, 1)
        self._layout.addWidget(grid_container)

        for column, text in enumerate(headers):
            label = QLabel(text)
            label.setObjectName("TableHeader")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            if column == 0:
                label.setFixedWidth(34)
            grid.addWidget(label, 0, column)

        for row_index, row in enumerate(rows, start=1):
            values = (
                row.chamber_label,
                f"[{row.team1_time}] {row.team1_seconds}s",
                f"[{row.team2_time}] {row.team2_seconds}s",
                row.factual_team1,
                row.factual_team2,
                row.sim_team1,
                row.sim_team2,
            )
            for column, text in enumerate(values):
                label = QLabel(text)
                label.setObjectName("TableCellPrimary" if column == 0 else "TableCell")
                label.setAlignment(
                    Qt.AlignmentFlag.AlignLeft
                    if column == 0
                    else Qt.AlignmentFlag.AlignCenter
                )
                if column == 0:
                    label.setFixedWidth(34)
                grid.addWidget(label, row_index, column)

        bottom = QHBoxLayout()
        bottom.setSpacing(8)
        self._layout.addLayout(bottom)

        total = QLabel(f"Total: {total_seconds}s")
        total.setObjectName("SummaryLine")
        bottom.addWidget(total, 1)

        status = QLabel(gcsim_status.status)
        status.setObjectName("SubtleText")
        bottom.addWidget(status)

        button = QPushButton(gcsim_status.button_label)
        button.setObjectName("GhostButton")
        button.setEnabled(False)
        bottom.addWidget(button)


class DetailRowWidget(QWidget):
    def __init__(self, *, metric: bool, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(7)

        self._icon = QLabel("")
        self._icon.setObjectName("MetricIcon" if metric else "StatIcon")
        self._icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._icon.setFixedSize(40, 24)
        layout.addWidget(self._icon)

        self._value = QLabel("")
        self._value.setObjectName("MetricValue" if metric else "StatValue")
        self._value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self._value, 1)

    def set_model(self, row: RightPanelDetailRowViewModel) -> None:
        self._icon.setText(row.icon_label or row.label[:2].upper())
        self._value.setText(row.value)

    def clear(self) -> None:
        self._icon.setText("")
        self._value.setText("")


class SelectedCharacterDetailsWidget(QFrame):
    external_bonuses_toggled = Signal(bool)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("DetailsBlock")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(10, 10, 10, 10)
        self._layout.setSpacing(8)
        self._mode = "empty"
        self._stat_rows: list[DetailRowWidget] = []
        self._chip_labels: list[QLabel] = []
        self._weapon_tooltip_controller = None
        self._weapon_name_tooltip_controller = None
        self._weapon_meta_tooltip_controller = None
        self._stable_selected_height = 0
        self._build_stable_skeleton()

    def set_details(self, details: RightPanelSelectedDetailsViewModel) -> None:
        total_start = perf_now()
        height_before = self.height()
        hint_before = self.sizeHint().height()

        if not details.has_selection:
            mode = self._show_empty_mode()
            log_perf(
                "right_panel_details_set",
                total=perf_ms(total_start),
                mode=mode,
                empty=True,
                height_before=height_before,
                height_after=self.height(),
                hint_before=hint_before,
                hint_after=self.sizeHint().height(),
            )
            return

        body_start = perf_now()
        mode = self._show_selected_mode()
        self._set_stat_rows(details.stat_rows)
        self._set_meta_details(details)
        body_ms = perf_ms(body_start)

        bonus_start = perf_now()
        bonus_mode = self._bonus_strip.set_items(
            details.bonus_sources,
            external_bonuses_enabled=details.external_bonuses_enabled,
        )
        self._remember_selected_height()
        bonus_ms = perf_ms(bonus_start)
        log_perf(
            "right_panel_details_set",
            total=perf_ms(total_start),
            mode=mode,
            empty=False,
            body=body_ms,
            bonus_strip=bonus_ms,
            bonus_mode=bonus_mode,
            bonus_count=len(details.bonus_sources),
            height_before=height_before,
            height_after=self.height(),
            hint_before=hint_before,
            hint_after=self.sizeHint().height(),
        )

    def _build_stable_skeleton(self) -> None:
        self._empty_label = QLabel("No selected character.")
        self._empty_label.setObjectName("SubtleText")
        self._empty_label.setWordWrap(True)
        self._layout.addWidget(self._empty_label)

        self._body = QWidget()
        self._body_layout = QHBoxLayout(self._body)
        self._body_layout.setContentsMargins(0, 0, 0, 0)
        self._body_layout.setSpacing(10)
        self._layout.addWidget(self._body)

        self._stats_frame = QFrame()
        self._stats_frame.setObjectName("StatsPanel")
        self._stats_frame.setMinimumHeight(128)
        self._stats_layout = QVBoxLayout(self._stats_frame)
        self._stats_layout.setContentsMargins(8, 8, 8, 8)
        self._stats_layout.setSpacing(6)
        self._stats_layout.addStretch(1)
        self._body_layout.addWidget(self._stats_frame, 2)

        self._meta_frame = QFrame()
        self._meta_frame.setObjectName("MetaPanel")
        self._meta_frame.setMinimumHeight(128)
        self._meta_layout = QVBoxLayout(self._meta_frame)
        self._meta_layout.setContentsMargins(8, 8, 8, 8)
        self._meta_layout.setSpacing(6)
        self._body_layout.addWidget(self._meta_frame, 3)

        self._name = QLabel("")
        self._name.setObjectName("DetailsName")
        self._name.setWordWrap(True)
        self._meta_layout.addWidget(self._name)

        self._chips_row = QWidget()
        self._chips_layout = QHBoxLayout(self._chips_row)
        self._chips_layout.setContentsMargins(0, 0, 0, 0)
        self._chips_layout.setSpacing(5)
        self._chips_layout.addStretch(1)
        self._meta_layout.addWidget(self._chips_row)

        self._weapon_frame = QFrame()
        self._weapon_frame.setObjectName("MetaSummaryBox")
        self._weapon_frame.setMinimumHeight(62)
        weapon_layout = QHBoxLayout(self._weapon_frame)
        weapon_layout.setContentsMargins(6, 6, 6, 6)
        weapon_layout.setSpacing(8)
        self._meta_layout.addWidget(self._weapon_frame)

        self._weapon_icon = QLabel("WPN")
        self._weapon_icon.setObjectName("DetailsWeaponIcon")
        self._weapon_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._weapon_icon.setFixedSize(48, 48)
        weapon_layout.addWidget(self._weapon_icon, alignment=Qt.AlignmentFlag.AlignLeft)

        weapon_text_column = QVBoxLayout()
        weapon_text_column.setContentsMargins(0, 0, 0, 0)
        weapon_text_column.setSpacing(4)
        weapon_layout.addLayout(weapon_text_column, 1)

        self._weapon_name = QLabel("")
        self._weapon_name.setObjectName("MetaValueStrong")
        self._weapon_name.setWordWrap(True)
        weapon_text_column.addWidget(self._weapon_name)

        self._weapon_meta = QLabel("")
        self._weapon_meta.setObjectName("MetaValue")
        self._weapon_meta.setWordWrap(True)
        weapon_text_column.addWidget(self._weapon_meta)
        weapon_text_column.addStretch(1)

        self._cv_frame = QFrame()
        self._cv_frame.setObjectName("MetaSummaryBox")
        self._cv_frame.setMinimumHeight(32)
        cv_layout = QHBoxLayout(self._cv_frame)
        cv_layout.setContentsMargins(8, 5, 8, 5)
        cv_layout.setSpacing(8)
        self._meta_layout.addWidget(self._cv_frame)

        self._cv_key = QLabel("CV")
        self._cv_key.setObjectName("MetaLabel")
        cv_layout.addWidget(self._cv_key)

        self._cv_value = QLabel("")
        self._cv_value.setObjectName("MetaValueStrong")
        self._cv_value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        cv_layout.addWidget(self._cv_value, 1)
        self._meta_layout.addStretch(1)

        self._bonus_strip = BonusSourceStripWidget()
        self._bonus_strip.external_bonuses_toggled.connect(self.external_bonuses_toggled.emit)
        self._layout.addWidget(self._bonus_strip)
        self._body.hide()
        self._bonus_strip.hide()

    def _show_empty_mode(self) -> str:
        if self._mode == "empty":
            return "empty_unchanged"
        self._empty_label.show()
        self._body.hide()
        self._bonus_strip.hide()
        if self._stable_selected_height:
            self.setMinimumHeight(self._stable_selected_height)
        self._mode = "empty"
        return "rebuild"

    def _show_selected_mode(self) -> str:
        if self._mode == "selected":
            return "skeleton_update"
        self._empty_label.hide()
        self._body.show()
        self._bonus_strip.show()
        self._mode = "selected"
        return "rebuild"

    def _remember_selected_height(self) -> None:
        height = max(self.sizeHint().height(), self.minimumHeight())
        if height <= self._stable_selected_height:
            return
        self._stable_selected_height = height
        self.setMinimumHeight(height)

    def _set_stat_rows(self, rows: tuple[RightPanelDetailRowViewModel, ...]) -> None:
        while len(self._stat_rows) < len(rows):
            widget = DetailRowWidget(metric=False)
            self._stats_layout.insertWidget(len(self._stat_rows), widget)
            self._stat_rows.append(widget)
        for index, widget in enumerate(self._stat_rows):
            if index < len(rows):
                widget.set_model(rows[index])
                widget.show()
            else:
                widget.clear()
                widget.hide()

    def _set_meta_details(self, details: RightPanelSelectedDetailsViewModel) -> None:
        self._name.setText(details.character_name)
        self._set_character_chips(_character_chips(details))
        self._set_weapon_summary(details)
        self._set_cv_summary(details.crit_value)

    def _set_character_chips(self, values: list[str]) -> None:
        while len(self._chip_labels) < len(values):
            chip = QLabel("")
            chip.setObjectName("MetaChip")
            chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._chips_layout.insertWidget(len(self._chip_labels), chip)
            self._chip_labels.append(chip)
        for index, chip in enumerate(self._chip_labels):
            if index < len(values):
                chip.setText(values[index])
                chip.show()
            else:
                chip.setText("")
                chip.hide()

    def _set_weapon_summary(self, details: RightPanelSelectedDetailsViewModel) -> None:
        has_weapon = bool(details.weapon_name or details.weapon_icon_path)
        weapon_bits = []
        if details.weapon_refinement is not None:
            weapon_bits.append(f"R{details.weapon_refinement}")
        if details.weapon_level is not None:
            weapon_bits.append(f"Lv.{details.weapon_level}")
        if details.weapon_base_atk:
            weapon_bits.append(f"ATK {details.weapon_base_atk}")
        if details.weapon_secondary_label and details.weapon_secondary_value:
            weapon_bits.append(
                f"{details.weapon_secondary_label} {details.weapon_secondary_value}"
            )

        self._weapon_icon.clear()
        self._weapon_icon.setText("WPN" if has_weapon else "")
        pixmap = _fit_pixmap(details.weapon_icon_path, QSize(50, 50))
        if pixmap is not None:
            self._weapon_icon.setText("")
            self._weapon_icon.setPixmap(pixmap)
        self._weapon_name.setText(details.weapon_name)
        self._weapon_meta.setText(" / ".join(weapon_bits))
        self._weapon_tooltip_controller = _set_custom_tooltip_text(
            self._weapon_icon,
            self._weapon_tooltip_controller,
            details.weapon_tooltip,
        )
        self._weapon_name_tooltip_controller = _set_custom_tooltip_text(
            self._weapon_name,
            self._weapon_name_tooltip_controller,
            details.weapon_tooltip,
        )
        self._weapon_meta_tooltip_controller = _set_custom_tooltip_text(
            self._weapon_meta,
            self._weapon_meta_tooltip_controller,
            details.weapon_tooltip,
        )

    def _set_cv_summary(self, crit_value: float | None) -> None:
        self._cv_value.setText(f"{crit_value:g}" if crit_value is not None else "")


class BonusSourceStripWidget(QFrame):
    external_bonuses_toggled = Signal(bool)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("BonusSourceStrip")
        self._items_key: tuple[object, ...] | None = None
        self._external_bonuses_enabled = True
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(30)
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._scroll = HorizontalDragScrollArea(wheel_step=40)
        self._scroll.setObjectName("BonusSourceScroll")
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setFixedHeight(28)
        self._scroll.clicked.connect(self._toggle_external_bonuses)
        root.addWidget(self._scroll)

        self._content = QWidget()
        self._layout = QHBoxLayout(self._content)
        self._layout.setContentsMargins(0, 1, 0, 1)
        self._layout.setSpacing(5)
        self._scroll.setWidget(self._content)

    def set_items(
        self,
        items: tuple[RightPanelBonusSourceDisplayItem, ...],
        *,
        external_bonuses_enabled: bool,
    ) -> str:
        items_key = _bonus_source_strip_key(items)
        if items_key == self._items_key:
            external_bonuses_enabled = bool(external_bonuses_enabled)
            if external_bonuses_enabled == self._external_bonuses_enabled:
                return "unchanged"
            self._set_external_bonuses_enabled(external_bonuses_enabled)
            return "in_place"

        self._items_key = items_key
        self._external_bonuses_enabled = bool(external_bonuses_enabled)
        _clear_layout(self._layout)
        self._set_external_bonuses_enabled(external_bonuses_enabled)
        if not items:
            empty = QLabel("No external bonuses")
            empty.setObjectName("BonusStripEmpty")
            empty.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            self._layout.addWidget(empty)
            self._layout.addStretch(1)
            return "rebuild_chips"
        for item in items:
            chip = BonusSourceChipWidget(item)
            chip.installEventFilter(self)
            self._layout.addWidget(chip)
        self._layout.addStretch(1)
        return "rebuild_chips"

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._toggle_external_bonuses()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _toggle_external_bonuses(self) -> None:
        self.external_bonuses_toggled.emit(not self._external_bonuses_enabled)

    def _set_external_bonuses_enabled(self, enabled: bool) -> None:
        self._external_bonuses_enabled = bool(enabled)
        self.setProperty("active", self._external_bonuses_enabled)
        self.style().unpolish(self)
        self.style().polish(self)

    def eventFilter(self, watched, event) -> bool:
        if event.type() == QEvent.Type.MouseButtonRelease:
            if event.button() == Qt.MouseButton.LeftButton:
                self._toggle_external_bonuses()
                return True
        return super().eventFilter(watched, event)


def _bonus_source_strip_key(
    items: tuple[RightPanelBonusSourceDisplayItem, ...],
) -> tuple[object, ...]:
    return (
        tuple(
            (
                item.source_kind,
                item.source_id,
                item.label,
                item.icon_path,
                tuple(item.short_effects),
                item.tooltip_title,
                item.tooltip_body,
                bool(item.applied),
                item.not_applied_reason,
                tuple(item.character_icons),
                tuple(item.character_tooltips),
            )
            for item in items
        ),
    )


class BonusSourceChipWidget(QFrame):
    def __init__(
        self,
        item: RightPanelBonusSourceDisplayItem,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setObjectName("BonusSourceChip")
        self.setProperty("disabled", not item.applied)
        self.setFixedHeight(24)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 1, 4, 1)
        layout.setSpacing(3)

        icon = QLabel(item.label[:3].upper() if item.label else "BON")
        icon.setObjectName("BonusSourceIcon")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setFixedSize(22, 22)
        icon.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents,
            not bool(item.character_tooltips),
        )
        pixmap = (
            _bonus_source_icon_pixmap(item.icon_path, QSize(22, 22))
            if item.icon_path
            else None
        )
        if pixmap is not None:
            icon.setText("")
            icon.setPixmap(pixmap)
        layout.addWidget(icon)

        for index, path in enumerate(item.character_icons[:4]):
            member_icon = QLabel("")
            member_icon.setObjectName("BonusSourceMemberIcon")
            member_icon.setFixedSize(22, 22)
            member_pixmap = _bonus_member_side_icon_pixmap(path, QSize(22, 22)) if path else None
            if member_pixmap is not None:
                member_icon.setPixmap(member_pixmap)
                if index < len(item.character_tooltips) and item.character_tooltips[index]:
                    install_custom_tooltip(member_icon, item.character_tooltips[index])
                layout.addWidget(member_icon)

        if item.short_effects:
            for effect_text in item.short_effects:
                badge = QLabel(effect_text)
                badge.setObjectName("BonusSourceEffectBadge")
                badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
                badge.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
                layout.addWidget(badge)
        elif not item.character_icons:
            fallback = QLabel(item.label)
            fallback.setObjectName("BonusSourceEffectBadge")
            fallback.setAlignment(Qt.AlignmentFlag.AlignCenter)
            fallback.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            layout.addWidget(fallback)

        tooltip = _bonus_source_tooltip_html(item)
        if tooltip:
            if item.character_tooltips:
                install_custom_tooltip(icon, tooltip)
            else:
                install_custom_tooltip(self, tooltip)


def _bonus_source_tooltip_html(item: RightPanelBonusSourceDisplayItem) -> str:
    rows: list[str] = []
    title = html.escape(item.tooltip_title or item.label)
    if title:
        rows.append(f"<b>{title}</b>")
    effect_lines = _unique_text_lines(tuple(item.short_effects))
    if effect_lines:
        rows.append(
            "<b>Effects:</b><br>"
            + "<br>".join(f"- {html.escape(line)}" for line in effect_lines)
        )
    if not item.applied and item.not_applied_reason:
        rows.append(
            f"<span style='color:#f09c9c;'>{html.escape(item.not_applied_reason)}</span>"
        )
    if item.tooltip_body:
        body_lines = _filtered_bonus_tooltip_body_lines(
            item.tooltip_body,
            title=item.tooltip_title or item.label,
            effects=effect_lines,
        )
        if body_lines:
            rows.append("<br>".join(html.escape(line) for line in body_lines))
    return "<br>".join(rows)


def _unique_text_lines(lines: tuple[str, ...]) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for line in lines:
        text = str(line or "").strip()
        key = text.casefold()
        if not text or key in seen:
            continue
        result.append(text)
        seen.add(key)
    return tuple(result)


def _filtered_bonus_tooltip_body_lines(
    body: str,
    *,
    title: str,
    effects: tuple[str, ...],
) -> tuple[str, ...]:
    title_key = str(title or "").strip().casefold()
    effect_keys = {effect.casefold() for effect in effects}
    result: list[str] = []
    seen: set[str] = set()
    for raw_line in str(body or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        key = line.casefold()
        if key == title_key or key in effect_keys or key in seen:
            continue
        if key.startswith("effects:"):
            continue
        result.append(line)
        seen.add(key)
    return tuple(result)


class ActionBarPrototypeWidget(QFrame):
    def __init__(
        self,
        labels: tuple[str, ...],
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setObjectName("ActionBar")
        self._labels: tuple[str, ...] | None = None
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(8)
        self.set_labels(labels)

    def set_labels(self, labels: tuple[str, ...]) -> None:
        labels = tuple(labels)
        if labels == self._labels:
            return
        self._labels = labels
        _clear_layout(self._layout)
        standard_icons = [
            QStyle.StandardPixmap.SP_BrowserReload,
            QStyle.StandardPixmap.SP_DialogSaveButton,
            QStyle.StandardPixmap.SP_FileDialogDetailedView,
        ]
        style = QApplication.style()
        for index, label in enumerate(labels):
            button = QPushButton(label)
            button.setObjectName("ActionButton")
            if index < len(standard_icons):
                button.setIcon(style.standardIcon(standard_icons[index]))
            self._layout.addWidget(button)


def _detail_row_layout(
    row: RightPanelDetailRowViewModel,
    *,
    metric: bool,
) -> QHBoxLayout:
    layout = QHBoxLayout()
    layout.setSpacing(7)

    icon = QLabel(row.icon_label or row.label[:2].upper())
    icon.setObjectName("MetricIcon" if metric else "StatIcon")
    icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
    icon.setFixedSize(40, 24)
    layout.addWidget(icon)

    value = QLabel(row.value)
    value.setObjectName("MetricValue" if metric else "StatValue")
    value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    layout.addWidget(value, 1)
    return layout


def _character_chips(details: RightPanelSelectedDetailsViewModel) -> list[str]:
    chips: list[str] = []
    if details.constellation is not None:
        chips.append(f"C{details.constellation}")
    if details.character_level is not None:
        chips.append(f"Lv.{details.character_level}")
    if details.element:
        chips.append(details.element.upper())
    return chips


def _build_mini_set_stack_pixmap(
    active_sets: tuple[RightPanelBuildMiniSetViewModel, ...],
) -> QPixmap | None:
    active_sets = tuple(active_sets[:2])
    if not active_sets:
        return None

    icons: list[QPixmap] = []
    for item in active_sets:
        if not item.icon_path:
            continue
        icon = _build_mini_set_icon_pixmap(item.icon_path)
        if icon is not None and not icon.isNull():
            icons.append(icon)

    if len(active_sets) == 2 and len(icons) == 2:
        composite = make_diagonal_split_pixmap(
            icons[0],
            icons[1],
            width=SLOT_EQUIP_ICON_SIZE,
            height=SLOT_EQUIP_ICON_SIZE,
            feather=SLOT_BUILD_BONUS_FEATHER,
        )
        return draw_count_badge(composite, "2")

    if len(active_sets) == 1 and len(icons) == 1:
        count = active_sets[0].piece_count
        badge = str(count) if count in (2, 4) else ""
        return draw_count_badge(icons[0], badge) if badge else icons[0]

    return None


def _build_mini_set_icon_pixmap(path: str) -> QPixmap | None:
    if not path:
        return None
    resolved = _resolve_pixmap_path(path)
    try:
        stat = resolved.stat()
        key = (
            str(resolved),
            SLOT_EQUIP_ICON_SIZE,
            SLOT_EQUIP_ICON_SIZE,
            int(stat.st_mtime_ns),
            int(stat.st_size),
        )
    except OSError:
        key = (
            str(path),
            SLOT_EQUIP_ICON_SIZE,
            SLOT_EQUIP_ICON_SIZE,
            0,
            0,
        )

    if key in _BUILD_MINI_SET_ICON_PIXMAP_CACHE:
        cached = _BUILD_MINI_SET_ICON_PIXMAP_CACHE[key]
        return QPixmap(cached) if cached is not None else None

    if not resolved.is_file():
        _BUILD_MINI_SET_ICON_PIXMAP_CACHE[key] = None
        return None

    pixmap = QPixmap(str(resolved))
    if pixmap.isNull():
        _BUILD_MINI_SET_ICON_PIXMAP_CACHE[key] = None
        return None
    result = _scale_trimmed_icon_for_chip(
        pixmap,
        SLOT_EQUIP_ICON_SIZE,
        SLOT_EQUIP_ICON_SIZE,
        padding=1,
        alpha_threshold=16,
    )
    _BUILD_MINI_SET_ICON_PIXMAP_CACHE[key] = QPixmap(result)
    return result


def _build_mini_set_fallback_text(
    active_sets: tuple[RightPanelBuildMiniSetViewModel, ...],
) -> str:
    if len(active_sets) >= 2:
        return "+".join(str(item.piece_count) for item in active_sets[:2])
    if active_sets:
        return f"{active_sets[0].piece_count}p"
    return "Build"


def _build_mini_set_tooltip(
    active_sets: tuple[RightPanelBuildMiniSetViewModel, ...],
) -> str:
    rows = [
        f"{item.piece_count}p {item.set_name}"
        for item in active_sets[:2]
        if item.set_name
    ]
    return " / ".join(rows)


def _build_mini_set_tooltip_html(
    active_sets: tuple[RightPanelBuildMiniSetViewModel, ...],
) -> str:
    rows = _build_mini_set_tooltip_rows(active_sets)
    rendered_rows: list[str] = []
    for piece_count, description in rows:
        description_html = html.escape(description).replace("\n", "<br>")
        rendered_rows.append(
            "<tr>"
            "<td valign='top' style='padding: 1px 8px 5px 0;'>"
            "<span style='"
            "background-color: #4a3b22; "
            "color: #f0d58a; "
            "border: 1px solid #8f7440; "
            "border-radius: 5px; "
            "font-weight: 800; "
            "padding: 1px 6px;"
            f"'>{int(piece_count)}</span>"
            "</td>"
            "<td valign='top' style='padding: 1px 0 5px 0;'>"
            f"{description_html}"
            "</td>"
            "</tr>"
        )
    if not rendered_rows:
        return _build_mini_set_tooltip(active_sets)
    return (
        "<table cellspacing='0' cellpadding='0' "
        "style='color: #f4ead8; font-size: 12px; font-weight: 600;'>"
        f"{''.join(rendered_rows)}"
        "</table>"
    )


def _build_mini_set_tooltip_rows(
    active_sets: tuple[RightPanelBuildMiniSetViewModel, ...],
) -> list[tuple[int, str]]:
    descriptions = _set_bonus_descriptions()
    rows: list[tuple[int, str]] = []
    for item in active_sets[:2]:
        if not item.set_uid:
            continue
        piece_counts = (2, 4) if item.piece_count >= 4 else (2,) if item.piece_count >= 2 else ()
        for piece_count in piece_counts:
            description = _clean_set_bonus_description(
                descriptions.get((item.set_uid, piece_count), "")
            )
            if description:
                rows.append((piece_count, description))
    return rows


@lru_cache(maxsize=1)
def _set_bonus_descriptions() -> dict[tuple[str, int], str]:
    try:
        return list_set_bonus_description_map()
    except Exception:
        return {}


def _clean_set_bonus_description(description: str) -> str:
    text = str(description or "").strip()
    if not text:
        return ""
    text = re.sub(r"</p>\s*<p[^>]*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</?p[^>]*>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\s*\n\s*", "\n", text)
    return text.strip()


def _fit_pixmap(path: str, size: QSize) -> QPixmap | None:
    if not path:
        return None
    resolved = _resolve_pixmap_path(path)
    if not resolved.is_file():
        key = (str(path), int(size.width()), int(size.height()))
        _FIT_PIXMAP_CACHE[key] = None
        return None
    key = (str(resolved), int(size.width()), int(size.height()))
    if key in _FIT_PIXMAP_CACHE:
        cached = _FIT_PIXMAP_CACHE[key]
        return QPixmap(cached) if cached is not None else None

    source = QPixmap(str(resolved))
    if source.isNull():
        _FIT_PIXMAP_CACHE[key] = None
        return None

    scaled = source.scaled(
        size,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )

    canvas = QPixmap(size)
    canvas.fill(Qt.GlobalColor.transparent)
    painter = QPainter(canvas)
    x = max(0, (size.width() - scaled.width()) // 2)
    y = max(0, (size.height() - scaled.height()) // 2)
    painter.drawPixmap(x, y, scaled)
    painter.end()
    _FIT_PIXMAP_CACHE[key] = QPixmap(canvas)
    return canvas


def _bonus_source_icon_pixmap(path: str, size: QSize) -> QPixmap | None:
    if not path:
        return None
    resolved = _resolve_pixmap_path(path)
    try:
        stat = resolved.stat()
        key = (
            str(resolved),
            int(size.width()),
            int(size.height()),
            int(stat.st_mtime_ns),
            int(stat.st_size),
        )
    except OSError:
        key = (str(path), int(size.width()), int(size.height()), 0, 0)

    if key in _BONUS_SOURCE_ICON_PIXMAP_CACHE:
        cached = _BONUS_SOURCE_ICON_PIXMAP_CACHE[key]
        return QPixmap(cached) if cached is not None else None

    if not resolved.is_file():
        _BONUS_SOURCE_ICON_PIXMAP_CACHE[key] = None
        return None

    source = QPixmap(str(resolved))
    if source.isNull():
        _BONUS_SOURCE_ICON_PIXMAP_CACHE[key] = None
        return None

    pixmap = _scale_trimmed_icon_for_chip(
        source,
        int(size.width()),
        int(size.height()),
        padding=1,
        alpha_threshold=4,
    )
    _BONUS_SOURCE_ICON_PIXMAP_CACHE[key] = QPixmap(pixmap)
    return pixmap


def _resolve_pixmap_path(path: str) -> Path:
    resolved = Path(path)
    if resolved.is_absolute():
        return resolved
    project_path = _PROJECT_ROOT / resolved
    if project_path.is_file():
        return project_path
    return resolved


def _bonus_member_side_icon_pixmap(path: str, size: QSize) -> QPixmap | None:
    if not path:
        return None
    resolved = _resolve_pixmap_path(path)
    try:
        stat = resolved.stat()
        key = (
            str(resolved),
            int(size.width()),
            int(size.height()),
            BONUS_MEMBER_ICON_SCALE,
            BONUS_MEMBER_ICON_BOTTOM_PADDING,
            int(stat.st_mtime_ns),
            int(stat.st_size),
        )
    except OSError:
        key = (
            str(path),
            int(size.width()),
            int(size.height()),
            BONUS_MEMBER_ICON_SCALE,
            BONUS_MEMBER_ICON_BOTTOM_PADDING,
            0,
            0,
        )

    if key in _BONUS_MEMBER_SIDE_ICON_PIXMAP_CACHE:
        cached = _BONUS_MEMBER_SIDE_ICON_PIXMAP_CACHE[key]
        return QPixmap(cached) if cached is not None else None

    if not resolved.is_file():
        _BONUS_MEMBER_SIDE_ICON_PIXMAP_CACHE[key] = None
        return None

    source = QPixmap(str(resolved))
    if source.isNull():
        _BONUS_MEMBER_SIDE_ICON_PIXMAP_CACHE[key] = None
        return None

    target_height = max(1, int(round(size.height() * BONUS_MEMBER_ICON_SCALE / 100)))
    scaled = source.scaledToHeight(
        target_height,
        Qt.TransformationMode.SmoothTransformation,
    )
    canvas = QPixmap(size)
    canvas.fill(Qt.GlobalColor.transparent)
    painter = QPainter(canvas)
    x = (size.width() - scaled.width()) // 2
    y = size.height() - scaled.height() - BONUS_MEMBER_ICON_BOTTOM_PADDING
    painter.drawPixmap(x, y, scaled)
    painter.end()
    _BONUS_MEMBER_SIDE_ICON_PIXMAP_CACHE[key] = QPixmap(canvas)
    return canvas


def _set_object_name(widget: QWidget, object_name: str) -> None:
    if widget.objectName() == object_name:
        return
    widget.setObjectName(object_name)
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


def _set_custom_tooltip_text(owner: QWidget, controller, text: str):
    text = str(text or "")
    if controller is not None:
        controller.set_text(text)
        return controller
    if text:
        return install_custom_tooltip(owner, text)
    QWidget.setToolTip(owner, "")
    return None


def _scale_trimmed_icon_for_chip(
    source: QPixmap,
    width: int,
    height: int,
    *,
    padding: int,
    alpha_threshold: int,
) -> QPixmap:
    prescale_width = max(1, int(width) * 2)
    prescale_height = max(1, int(height) * 2)
    prescaled = source.scaled(
        prescale_width,
        prescale_height,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    return scale_trimmed_pixmap_to_size(
        prescaled,
        width,
        height,
        padding=padding,
        alpha_threshold=alpha_threshold,
    )


def _clear_layout(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        child_layout = item.layout()
        if widget is not None:
            widget.deleteLater()
        elif child_layout is not None:
            _clear_layout(child_layout)


def _stylesheet() -> str:
    return """
    #RightPanelPrototypeContent {
        background: #17191d;
        color: #edf0f2;
        font-size: 12px;
    }
    #ModeTabButton {
        min-height: 30px;
        border: 1px solid #3a3f49;
        border-radius: 6px;
        background: #22262d;
        color: #ccd3d9;
        font-weight: 600;
    }
    #ModeTabButton:checked {
        background: #d7b461;
        color: #17191d;
        border-color: #f1d486;
    }
    #TeamSlotRow, #InfoBlock, #DetailsBlock {
        border: 1px solid #363b43;
        border-radius: 8px;
        background: #202329;
    }
    #SectionTitle {
        color: #f1d486;
        font-weight: 800;
        font-size: 13px;
    }
    #SlotCard, #SlotCardSelected {
        border: 2px solid #3f4652;
        border-radius: 7px;
        background: #292e37;
    }
    #SlotCardSelected {
        border-color: #d7b461;
        background: #303743;
    }
    #PortraitBox, #PortraitBoxEmpty {
        border-radius: 6px;
        border: 1px solid #52606d;
        background: #516679;
        color: #ffffff;
        font-size: 23px;
        font-weight: 900;
    }
    #PortraitBoxEmpty {
        background: #2b3037;
        color: #8b939c;
        border-style: dashed;
    }
    #MiniEquipBox, #MiniEquipBoxMissing {
        border-radius: 5px;
        border: 1px solid #626b78;
        background: #343a44;
        color: #edf2f5;
        font-size: 10px;
        font-weight: 800;
    }
    #MiniEquipBoxMissing {
        border-color: #b9825f;
        background: #4a382f;
        color: #ffd2ad;
    }
    #DetailsWeaponIcon {
        border-radius: 5px;
        border: 1px solid #626b78;
        background: #343a44;
        color: #edf2f5;
        font-size: 10px;
        font-weight: 800;
    }
    #MetaSummaryBox {
        border-radius: 5px;
        border: 1px solid #303741;
        background: #15181d;
    }
    #SlotName {
        color: #f8f3e7;
        font-weight: 800;
    }
    #StatBadge {
        min-height: 20px;
        border-radius: 4px;
        background: #111316;
        color: #e1e8ec;
        font-size: 9px;
        font-weight: 800;
        padding: 0px 1px;
    }
    #WarningBadge {
        min-height: 22px;
        border-radius: 4px;
        background: #8b3434;
        color: #fff3ef;
        font-size: 10px;
        font-weight: 900;
        padding: 0px 1px;
    }
    #TableHeader {
        color: #98c9bf;
        font-size: 10px;
        font-weight: 800;
    }
    #TableCell, #TableCellPrimary {
        min-height: 23px;
        border-radius: 4px;
        background: #15181d;
        color: #dce3e7;
        padding: 2px 5px;
        font-family: Consolas, "Courier New", monospace;
    }
    #TableCellPrimary {
        color: #f1d486;
        font-weight: 800;
        font-family: Arial, sans-serif;
    }
    #SummaryLine, #DetailsName {
        color: #ffffff;
        font-weight: 900;
    }
    #GhostButton, #ActionButton {
        border: 1px solid #4d5662;
        border-radius: 6px;
        background: #2d343d;
        color: #eef2f5;
        padding: 7px 10px;
        font-weight: 800;
    }
    #GhostButton:disabled {
        color: #9ca6ad;
        background: #242a31;
    }
    #SubtleText {
        color: #c7cdd2;
    }
    #StatsPanel, #MetaPanel {
        border: 1px solid #333941;
        border-radius: 6px;
        background: #181b20;
    }
    #MetricIcon, #StatIcon {
        border-radius: 4px;
        color: #111316;
        font-size: 10px;
        font-weight: 900;
    }
    #MetricIcon {
        background: #d7b461;
    }
    #StatIcon {
        background: #98c9bf;
    }
    #MetricValue, #StatValue {
        color: #edf2f5;
        font-weight: 800;
    }
    #MetaChip {
        border-radius: 4px;
        background: #314236;
        color: #d9f0df;
        font-size: 10px;
        font-weight: 900;
        padding: 3px 6px;
    }
    #MetaLabel {
        color: #98a7b1;
        font-size: 10px;
        font-weight: 700;
    }
    #MetaValue {
        color: #e6ecef;
        font-weight: 700;
    }
    #MetaValueStrong {
        color: #ffffff;
        font-weight: 900;
    }
    #SetsLine {
        border-radius: 5px;
        background: #111316;
        color: #f4ddb0;
        padding: 7px 8px;
        font-weight: 800;
    }
    #BonusSourceStrip {
        min-height: 28px;
        border-radius: 5px;
        border: 1px solid #3f4652;
        background: #111316;
        padding: 1px 3px;
    }
    #BonusSourceStrip[active="true"] {
        border-color: #d7b461;
        background: #15181d;
    }
    #BonusSourceStrip[active="false"] {
        border-color: #2d333b;
        background: #101216;
    }
    #BonusSourceScroll {
        background: transparent;
    }
    #BonusSourceChip {
        border: 1px solid #3f4652;
        border-radius: 5px;
        background: #222832;
    }
    #BonusSourceChip[disabled="true"] {
        border-color: #30343b;
        background: #191c21;
    }
    #BonusSourceChip[disabled="true"] #BonusSourceEffectBadge {
        color: #8f99a4;
        border-color: #30343b;
        background: #13161a;
    }
    #BonusSourceIcon {
        border-radius: 4px;
        background: transparent;
        border: none;
        color: #f4ddb0;
        font-size: 9px;
        font-weight: 900;
    }
    #BonusSourceMemberIcon {
        border-radius: 3px;
        border: none;
        background: transparent;
    }
    #BonusSourceEffectBadge {
        border-radius: 4px;
        border: 1px solid #3d4653;
        background: #151a20;
        color: #f4ddb0;
        font-size: 10px;
        font-weight: 900;
        padding: 1px 5px;
        min-height: 16px;
    }
    #BonusStripEmpty {
        color: #8f99a4;
        font-size: 11px;
        font-weight: 700;
        padding: 4px 8px;
    }
    #ActionBar {
        background: transparent;
    }
    """
