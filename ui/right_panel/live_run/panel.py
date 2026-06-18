from __future__ import annotations

import html
import os
import re
from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QByteArray, QEvent, QMimeData, QRect, QSize, Qt, Signal, QTimer
from PySide6.QtGui import QDrag, QIntValidator, QKeyEvent, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from localization import tr
from run_workspace.models import (
    adjust_abyss_timer_seconds_with_second_wheel,
    clamp_abyss_timer_edit_seconds,
)
from run_workspace.right_panel_prototype_view_model import (
    FactDpsEnemyTooltipViewModel,
    FactDpsTooltipViewModel,
    GcsimTooltipViewModel,
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
from ui.utils.hidpi_pixmap import (
    effective_pixmap_dpr,
    load_hidpi_pixmap,
    logical_pixmap_size,
    make_hidpi_canvas,
)
from run_workspace.perf import log_perf, perf_ms, perf_now
from ui.utils.drag_scroll import HorizontalDragScrollArea
from ui.utils.overlay_scroll import OverlayVerticalScrollArea
from ui.utils.tooltips import install_custom_tooltip
from ui.utils.owner_icon_badge import (
    make_owner_icon_badge_background,
    owner_badge_rect_for_icon_rect,
    owner_badge_size_for_icon,
)
from ui.artifact_browser.queries import list_set_bonus_description_map
from ui.utils.ui_palette import UI_STATE_DANGER, UI_STATE_SUCCESS, UI_TEXT_MUTED
from ui.right_panel.common.metrics import (
    ABYSS_CHAMBER_BADGE_WIDTH,
    ABYSS_CHAMBER_GRID_SPACING,
    ABYSS_DPS_COLUMN_MIN_WIDTH,
    ABYSS_FACT_DPS_LEFT_BUDGET_MAX,
    ABYSS_TIMER_CELL_WIDTH,
    ABYSS_TIMER_ELAPSED_WIDTH,
    ABYSS_TIMER_FRAME_WIDTH,
    ABYSS_TIMER_SEPARATOR_WIDTH,
    ABYSS_TIMER_SEGMENT_WIDTH,
    BONUS_MEMBER_ICON_SIZE,
    BONUS_MEMBER_ICON_SCALE,
    BONUS_MEMBER_ICON_BOTTOM_PADDING,
    BONUS_SOURCE_CHIP_HEIGHT,
    OWNER_BADGE_TRACE,
    RIGHT_PANEL_PROTOTYPE_CONTENT_MIN_WIDTH,
    RIGHT_PANEL_PROTOTYPE_MIN_WIDTH,
    _BONUS_MEMBER_SIDE_ICON_PIXMAP_CACHE,
    _BONUS_SOURCE_ICON_PIXMAP_CACHE,
    _clear_layout,
    _fit_pixmap,
    _resolve_pixmap_path,
    _scale_trimmed_icon_for_chip,
    _set_custom_tooltip_text,
    _trace_rect,
)
from ui.right_panel.common.team_card import RightPanelTeamCardWidget
from ui.right_panel.common.slot_card import (
    RightPanelSlotCardWidget,
    _clean_set_bonus_description,
)


class RunModeTabsWidget(QWidget):
    """Reusable run-page tabs with stable ids independent from display text."""

    mode_requested = Signal(str)

    def __init__(
        self,
        active_mode: str | None = MODE_ABYSS,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._tab_group = QButtonGroup(self)
        self._tab_group.setExclusive(True)
        self._buttons_by_mode: dict[str, QPushButton] = {}

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        for mode, label_key in (
            (MODE_ABYSS, "right_panel.mode.abyss"),
            (MODE_DPS_DUMMY, "right_panel.mode.dps_dummy"),
        ):
            button = make_mode_tab_button(tr(label_key))
            button.clicked.connect(
                lambda _checked=False, value=mode: self.mode_requested.emit(value)
            )
            self._tab_group.addButton(button)
            self._buttons_by_mode[mode] = button
            layout.addWidget(button, 1)

        self.set_active_mode(active_mode)

    def button_for_mode(self, mode: str) -> QPushButton:
        return self._buttons_by_mode[mode]

    def buttons(self) -> tuple[QPushButton, ...]:
        return tuple(self._buttons_by_mode.values())

    def set_active_mode(self, mode: str | None) -> None:
        if mode is None:
            self._tab_group.setExclusive(False)
        for button_mode, button in self._buttons_by_mode.items():
            button.setChecked(button_mode == mode)
        if mode is None:
            self._tab_group.setExclusive(True)

    def retranslate_ui(self) -> None:
        self._buttons_by_mode[MODE_ABYSS].setText(tr("right_panel.mode.abyss"))
        self._buttons_by_mode[MODE_DPS_DUMMY].setText(
            tr("right_panel.mode.dps_dummy")
        )


def make_mode_tab_button(text: str) -> QPushButton:
    button = QPushButton(text)
    button.setCheckable(True)
    button.setObjectName("ModeTabButton")
    return button


class RightPanelRunActionsWidget(QFrame):
    reset_requested = Signal()
    save_requested = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("RunActionBar")
        self._last_save_result: object | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        button_row = QWidget()
        button_layout = QHBoxLayout(button_row)
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(8)
        root.addWidget(button_row)

        self.reset_button = QPushButton(tr("app_shell.right_dock.reset"))
        self.reset_button.setObjectName("ActionButton")
        self.reset_button.clicked.connect(
            lambda _checked=False: self.reset_requested.emit()
        )
        button_layout.addWidget(self.reset_button, 1)

        self.save_button = QPushButton(tr("app_shell.right_dock.save"))
        self.save_button.setObjectName("ActionButton")
        self.save_button.clicked.connect(
            lambda _checked=False: self.save_requested.emit()
        )
        button_layout.addWidget(self.save_button, 1)

        self.save_status_label = QLabel("")
        self.save_status_label.setObjectName("RunActionStatus")
        self.save_status_label.setWordWrap(True)
        self.save_status_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.save_status_label.setStyleSheet(
            f"color: {UI_TEXT_MUTED}; padding: 0px 2px;"
        )
        self.save_status_label.setVisible(False)
        root.addWidget(self.save_status_label)

    def show_save_result(self, result: object) -> None:
        self._last_save_result = result
        self._render_save_status()

    def clear_save_status(self) -> None:
        self._last_save_result = None
        self.save_status_label.clear()
        self.save_status_label.setVisible(False)

    def retranslate_ui(self) -> None:
        self.reset_button.setText(tr("app_shell.right_dock.reset"))
        self.save_button.setText(tr("app_shell.right_dock.save"))
        if self._last_save_result is not None:
            self._render_save_status()

    def _render_save_status(self) -> None:
        result = self._last_save_result
        if result is None:
            self.clear_save_status()
            return
        if bool(getattr(result, "success", False)):
            text = tr(
                "app_shell.right_dock.save_status.saved",
                bundle_id=str(getattr(result, "bundle_id", "")),
                path=str(getattr(result, "saved_path", "") or ""),
            )
            color = UI_STATE_SUCCESS
        else:
            text = tr(
                "app_shell.right_dock.save_status.failed",
                error=str(getattr(result, "error_text", "") or "unknown error"),
            )
            color = UI_STATE_DANGER
        self.save_status_label.setStyleSheet(
            f"color: {color}; padding: 0px 2px;"
        )
        self.save_status_label.setText(text)
        self.save_status_label.setVisible(True)


class RunRightPanelWidget(QWidget):
    """Current live Run/Abyss/DPS right-panel widget."""

    mode_requested = Signal(str)
    slot_selected = Signal(int, int)
    slot_dropped = Signal(int, int, int, int)
    external_bonuses_toggled = Signal(bool)
    abyss_timer_changed = Signal(int, int, int)
    reset_requested = Signal()
    save_requested = Signal()

    def __init__(
        self,
        model: RightPanelPrototypeViewModel,
        parent: QWidget | None = None,
        *,
        show_mode_tabs: bool = True,
        show_chamber_table: bool = True,
        show_run_actions: bool = True,
        read_only: bool = False,
    ):
        super().__init__(parent)
        self.setObjectName("RightPanelPrototypeWidget")
        self.setMinimumWidth(RIGHT_PANEL_PROTOTYPE_MIN_WIDTH)
        self._model = model
        self._team_widgets: list[RightPanelTeamCardWidget] = []
        self._slot_widgets: list[RightPanelSlotCardWidget] = []
        self._show_chamber_table = bool(show_chamber_table)
        self._show_run_actions = bool(show_run_actions)
        self._read_only = bool(read_only)

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

        self._mode_tabs: RunModeTabsWidget | None = None
        if show_mode_tabs:
            self._mode_tabs = RunModeTabsWidget(model.mode)
            self._mode_tabs.mode_requested.connect(self.mode_requested.emit)
            self._layout.addWidget(self._mode_tabs)

        self._teams_container = QWidget()
        self._teams_layout = QVBoxLayout(self._teams_container)
        self._teams_layout.setContentsMargins(0, 0, 0, 0)
        self._teams_layout.setSpacing(6)
        self._layout.addWidget(self._teams_container)

        self._chamber_table = ChamberTableBlockWidget(read_only=self._read_only)
        self._chamber_table.abyss_timer_changed.connect(
            self.abyss_timer_changed.emit
        )
        self._chamber_table.setVisible(self._show_chamber_table)
        self._layout.addWidget(self._chamber_table)

        self._details_frame = SelectedCharacterDetailsWidget(
            read_only=self._read_only
        )
        self._details_frame.external_bonuses_toggled.connect(
            self.external_bonuses_toggled.emit
        )
        self._layout.addWidget(self._details_frame)

        self._run_actions = RightPanelRunActionsWidget()
        self._run_actions.reset_requested.connect(self.reset_requested.emit)
        self._run_actions.save_requested.connect(self.save_requested.emit)
        self.reset_button = self._run_actions.reset_button
        self.save_button = self._run_actions.save_button
        self.save_status_label = self._run_actions.save_status_label
        self._run_actions.setVisible(self._show_run_actions)
        self._layout.addWidget(self._run_actions)

        self._layout.addStretch(1)

        self.setStyleSheet(right_panel_stylesheet())
        self.set_model(model)

    def set_model(self, model: RightPanelPrototypeViewModel) -> None:
        total_start = perf_now()
        updates_were_enabled = self.updatesEnabled()
        if updates_were_enabled:
            self.setUpdatesEnabled(False)
        QToolTip.hideText()
        self._model = model
        tabs_start = perf_now()
        if self._mode_tabs is not None:
            self._mode_tabs.set_active_mode(model.mode)
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
        if self._show_chamber_table:
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
        self._settle_content_layout()
        log_perf(
            "right_panel_set_model_widget",
            total=perf_ms(total_start),
            tabs=tabs_ms,
            teams=teams_ms,
            teams_mode=teams_mode,
            chamber=chamber_ms,
            details=details_ms,
        )
        if updates_were_enabled:
            QTimer.singleShot(0, self._finish_deferred_update)

    def show_save_result(self, result: object) -> None:
        if not self._show_run_actions:
            return
        self._run_actions.show_save_result(result)

    def clear_save_status(self) -> None:
        if not self._show_run_actions:
            return
        self._run_actions.clear_save_status()

    def retranslate_ui(self) -> None:
        if self._mode_tabs is not None:
            self._mode_tabs.retranslate_ui()
        if self._show_run_actions:
            self._run_actions.retranslate_ui()

    def recommended_standalone_size(self) -> QSize:
        self._content.adjustSize()
        hint = self._content.sizeHint()
        return QSize(
            max(RIGHT_PANEL_PROTOTYPE_MIN_WIDTH, hint.width()),
            max(1, hint.height() + self._scroll.frameWidth() * 2),
        )

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
            team_widget = RightPanelTeamCardWidget(
                team,
                allow_mutation=not self._read_only,
            )
            team_widget.slot_selected.connect(self.slot_selected.emit)
            team_widget.slot_dropped.connect(self.slot_dropped.emit)
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

    def _finish_deferred_update(self) -> None:
        self._settle_content_layout()
        self.setUpdatesEnabled(True)
        self.update()

    def event(self, event) -> bool:
        if event.type() in (
            QEvent.Type.DevicePixelRatioChange,
            QEvent.Type.ScreenChangeInternal,
        ):
            for slot_widget in self._slot_widgets:
                slot_widget.refresh_hidpi_pixmaps()
            self._details_frame.refresh_hidpi_pixmaps()
        return super().event(event)



class AbyssTimerSegmentEdit(QLineEdit):
    def __init__(
        self,
        timer: "CompactAbyssTimerWidget",
        segment: str,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._timer = timer
        self.segment = segment
        self.setMaxLength(2)
        self.setValidator(QIntValidator(0, 99, self))

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._timer.commit_segment(self)
            self.selectAll()
            event.accept()
            return
        if event.key() == Qt.Key.Key_Left:
            self._timer.commit_segment(self)
            self._timer.focus_segment("minutes")
            event.accept()
            return
        if event.key() == Qt.Key.Key_Right:
            self._timer.commit_segment(self)
            self._timer.focus_segment("seconds")
            event.accept()
            return
        if event.key() in (Qt.Key.Key_Up, Qt.Key.Key_Down):
            self._timer.adjust_segment(
                self.segment,
                1 if event.key() == Qt.Key.Key_Up else -1,
            )
            self.selectAll()
            event.accept()
            return
        super().keyPressEvent(event)

    def focusInEvent(self, event) -> None:
        super().focusInEvent(event)
        self.selectAll()

    def focusOutEvent(self, event) -> None:
        self._timer.commit_segment(self)
        super().focusOutEvent(event)

    def mousePressEvent(self, event) -> None:
        super().mousePressEvent(event)
        self.selectAll()

    def wheelEvent(self, event) -> None:
        delta_steps = event.angleDelta().y() // 120
        if delta_steps:
            self._timer.adjust_segment(self.segment, delta_steps)
            self.selectAll()
            event.accept()
            return
        super().wheelEvent(event)


class CompactAbyssTimerWidget(QFrame):
    seconds_changed = Signal(int)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("TimerEditorFrame")
        self._seconds_left = 600
        self._max_seconds = 600
        self._updating = False
        self._segment_dirty = {
            "minutes": False,
            "seconds": False,
        }
        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 0, 2, 0)
        layout.setSpacing(0)

        self.min_edit = AbyssTimerSegmentEdit(self, "minutes")
        self.min_edit.setObjectName("TimerSegmentEdit")
        self.min_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.min_edit.setFixedWidth(ABYSS_TIMER_SEGMENT_WIDTH)

        colon = QLabel(":")
        colon.setObjectName("TimerSeparator")
        colon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        colon.setFixedWidth(ABYSS_TIMER_SEPARATOR_WIDTH)

        self.sec_edit = AbyssTimerSegmentEdit(self, "seconds")
        self.sec_edit.setObjectName("TimerSegmentEdit")
        self.sec_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sec_edit.setFixedWidth(ABYSS_TIMER_SEGMENT_WIDTH)

        layout.addWidget(self.min_edit)
        layout.addWidget(colon)
        layout.addWidget(self.sec_edit)
        self.setFixedWidth(ABYSS_TIMER_FRAME_WIDTH)

        self.min_edit.textEdited.connect(
            lambda _text: self._mark_segment_dirty("minutes")
        )
        self.sec_edit.textEdited.connect(
            lambda _text: self._mark_segment_dirty("seconds")
        )
        self.set_seconds(600)

    @property
    def seconds_left(self) -> int:
        return self._seconds_left

    def set_seconds(self, seconds_left: int) -> None:
        self._set_seconds(seconds_left, emit=False)

    def set_max_seconds(self, max_seconds: int) -> None:
        self._max_seconds = clamp_abyss_timer_edit_seconds(max_seconds)
        self._set_seconds(self._seconds_left, emit=False)

    def adjust_seconds(self, delta_steps: int) -> None:
        self._set_seconds(
            adjust_abyss_timer_seconds_with_second_wheel(
                self._seconds_left,
                delta_steps,
                start_seconds=self._max_seconds,
            ),
            emit=True,
            force_sync=True,
        )

    def adjust_segment(self, segment: str, delta_steps: int) -> None:
        edit = self._edit_for_segment(segment)
        self.commit_segment(edit)
        multiplier = 60 if segment == "minutes" else 1
        self.adjust_seconds(int(delta_steps) * multiplier)

    def commit_segment(self, edit: AbyssTimerSegmentEdit) -> None:
        if self._updating:
            return
        segment = edit.segment
        if not self._segment_dirty[segment]:
            return
        value_text = edit.text().strip()
        if not value_text.isdigit():
            self._segment_dirty[segment] = False
            self._sync_segment_texts()
            return
        value = int(value_text)
        minutes, seconds = divmod(self._seconds_left, 60)
        if segment == "minutes":
            minutes = value
        else:
            seconds = min(value, 59)
        self._segment_dirty[segment] = False
        self._set_seconds(
            minutes * 60 + seconds,
            emit=True,
            force_sync=True,
        )

    def focus_segment(self, segment: str) -> None:
        destination = self._edit_for_segment(segment)
        focused = self.focusWidget()
        if isinstance(focused, AbyssTimerSegmentEdit):
            self.commit_segment(focused)
        destination.setFocus(Qt.FocusReason.TabFocusReason)
        destination.selectAll()

    def _edit_for_segment(self, segment: str) -> AbyssTimerSegmentEdit:
        return self.min_edit if segment == "minutes" else self.sec_edit

    def _mark_segment_dirty(self, segment: str) -> None:
        if not self._updating:
            self._segment_dirty[segment] = True

    def _set_seconds(
        self,
        seconds_left: int,
        *,
        emit: bool,
        force_sync: bool = False,
    ) -> None:
        seconds = clamp_abyss_timer_edit_seconds(
            seconds_left,
            start_seconds=self._max_seconds,
        )
        changed = seconds != self._seconds_left
        self._seconds_left = seconds
        if force_sync or changed or not any(self._segment_dirty.values()):
            self._sync_segment_texts()
        if emit and changed:
            self.seconds_changed.emit(seconds)

    def _sync_segment_texts(self) -> None:
        minutes, remainder = divmod(self._seconds_left, 60)
        self._updating = True
        try:
            self.min_edit.setText(f"{minutes:02d}")
            self.sec_edit.setText(f"{remainder:02d}")
            self._segment_dirty["minutes"] = False
            self._segment_dirty["seconds"] = False
        finally:
            self._updating = False


class ChamberTimerCellWidget(QWidget):
    seconds_changed = Signal(int)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("TimerTableCell")
        self.setFixedWidth(ABYSS_TIMER_CELL_WIDTH)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(1, 0, 0, 0)
        layout.setSpacing(1)
        self.timer = CompactAbyssTimerWidget()
        self.elapsed_label = QLabel("0s")
        self.elapsed_label.setObjectName("TimerElapsed")
        self.elapsed_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.elapsed_label.setFixedWidth(ABYSS_TIMER_ELAPSED_WIDTH)
        layout.addWidget(self.timer)
        layout.addWidget(self.elapsed_label)
        self.timer.seconds_changed.connect(self.seconds_changed.emit)

    def set_model(
        self,
        time_text: str,
        elapsed_seconds: int,
        *,
        max_seconds: int = 600,
    ) -> None:
        self.timer.set_max_seconds(max_seconds)
        self.timer.set_seconds(_remaining_seconds_from_time_text(time_text))
        self.elapsed_label.setText(f"{int(elapsed_seconds)}s")


class ChamberTableBlockWidget(QFrame):
    abyss_timer_changed = Signal(int, int, int)

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        read_only: bool = False,
    ):
        super().__init__(parent)
        self._read_only = bool(read_only)
        self.setObjectName("InfoBlock")
        self._layout = QVBoxLayout(self)
        self._structure_key: tuple[object, ...] | None = None
        self._content_key: tuple[object, ...] | None = None
        self._row_labels: dict[tuple[int, int], QLabel] = {}
        self._timer_cells: dict[tuple[int, int], ChamberTimerCellWidget] = {}
        self._fact_dps_tooltips: dict[tuple[int, int], object] = {}
        self._gcsim_tooltips: dict[tuple[int, int], object] = {}
        self._total_label: QLabel | None = None
        self._status_label: QLabel | None = None
        self._gcsim_button: QPushButton | None = None
        self._layout.setContentsMargins(8, 7, 8, 7)
        self._layout.setSpacing(4)

    def set_rows(
        self,
        headers: tuple[str, ...],
        rows: tuple[RightPanelChamberRowViewModel, ...],
        *,
        total_seconds: int,
        gcsim_status: RightPanelGcsimStatusViewModel,
    ) -> None:
        structure_key = (
            tuple(headers),
            tuple(
                (
                    row.chamber_label,
                    bool(row.timer_editable),
                )
                for row in rows
            ),
            gcsim_status.button_label,
        )
        content_key = (
            tuple(headers),
            tuple(row.to_dict().items() for row in rows),
            int(total_seconds),
            gcsim_status.status,
            gcsim_status.button_label,
        )
        if content_key == self._content_key:
            return
        if structure_key != self._structure_key:
            self._rebuild(headers, rows, gcsim_status=gcsim_status)
            self._structure_key = structure_key
        self._content_key = content_key
        self._update_rows(rows, total_seconds=total_seconds, gcsim_status=gcsim_status)

    def _rebuild(
        self,
        headers: tuple[str, ...],
        rows: tuple[RightPanelChamberRowViewModel, ...],
        *,
        gcsim_status: RightPanelGcsimStatusViewModel,
    ) -> None:
        _clear_layout(self._layout)
        self._row_labels = {}
        self._timer_cells = {}
        self._fact_dps_tooltips = {}
        self._gcsim_tooltips = {}

        grid_container = QWidget()
        grid = QGridLayout(grid_container)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(ABYSS_CHAMBER_GRID_SPACING)
        grid.setVerticalSpacing(4)
        grid.setColumnMinimumWidth(0, ABYSS_CHAMBER_BADGE_WIDTH)
        grid.setColumnStretch(0, 0)
        grid.setColumnMinimumWidth(1, ABYSS_TIMER_CELL_WIDTH)
        grid.setColumnMinimumWidth(2, ABYSS_TIMER_CELL_WIDTH)
        grid.setColumnStretch(1, 0)
        grid.setColumnStretch(2, 0)
        for column in range(3, 7):
            grid.setColumnMinimumWidth(column, ABYSS_DPS_COLUMN_MIN_WIDTH)
            grid.setColumnStretch(column, 1)
        self._layout.addWidget(grid_container)

        data_row_start = self._add_headers(grid, headers)

        for model_row_index, row in enumerate(rows):
            view_row_index = model_row_index + data_row_start
            for column in range(len(headers)):
                if row.timer_editable and column in (1, 2):
                    cell = ChamberTimerCellWidget()
                    team_number = column
                    if self._read_only:
                        cell.setEnabled(False)
                    else:
                        cell.seconds_changed.connect(
                            lambda seconds, row_index=model_row_index, team=team_number: (
                                self.abyss_timer_changed.emit(row_index, team, seconds)
                            )
                        )
                    self._timer_cells[(model_row_index, team_number)] = cell
                    grid.addWidget(cell, view_row_index, column)
                    continue
                label = QLabel("")
                if column == 0:
                    label.setObjectName("ChamberBadge")
                elif column in (3, 4):
                    label.setObjectName("FactDpsCell")
                    self._fact_dps_tooltips[(model_row_index, column)] = (
                        install_custom_tooltip(label, "")
                    )
                elif column in (5, 6):
                    label.setObjectName("TableCell")
                    self._gcsim_tooltips[(model_row_index, column)] = (
                        install_custom_tooltip(label, "")
                    )
                else:
                    label.setObjectName("TableCell")
                label.setAlignment(
                    Qt.AlignmentFlag.AlignCenter
                )
                if column == 0:
                    label.setFixedWidth(ABYSS_CHAMBER_BADGE_WIDTH)
                self._row_labels[(model_row_index, column)] = label
                grid.addWidget(label, view_row_index, column)

        bottom = QHBoxLayout()
        bottom.setSpacing(6)
        self._layout.addLayout(bottom)

        self._total_label = QLabel("")
        self._total_label.setObjectName("SummaryLine")
        bottom.addWidget(self._total_label, 1)

        self._status_label = QLabel("")
        self._status_label.setObjectName("SubtleText")
        bottom.addWidget(self._status_label)

        self._gcsim_button = QPushButton(gcsim_status.button_label)
        self._gcsim_button.setObjectName("GhostButton")
        self._gcsim_button.setEnabled(False)
        self._gcsim_button.setVisible(not self._read_only)
        bottom.addWidget(self._gcsim_button)

    @staticmethod
    def _add_headers(grid: QGridLayout, headers: tuple[str, ...]) -> int:
        if len(headers) != 7:
            for column, text in enumerate(headers):
                label = QLabel(text)
                label.setObjectName("TableHeader")
                label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                if column == 0:
                    label.setFixedWidth(ABYSS_CHAMBER_BADGE_WIDTH)
                grid.addWidget(label, 0, column)
            return 1

        for column, text in enumerate(headers[:3]):
            label = QLabel(text)
            label.setObjectName("TableHeader")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            if column == 0:
                label.setFixedWidth(ABYSS_CHAMBER_BADGE_WIDTH)
            grid.addWidget(label, 0, column, 2, 1)

        for column, text in ((3, "Fact DPS"), (5, "Sim DPS")):
            label = QLabel(text)
            label.setObjectName("TableHeader")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            grid.addWidget(label, 0, column, 1, 2)
            for team_offset, team_label in enumerate(("T1", "T2")):
                sub_label = QLabel(team_label)
                sub_label.setObjectName("TableSubHeader")
                sub_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                grid.addWidget(sub_label, 1, column + team_offset)
        return 2

    def _update_rows(
        self,
        rows: tuple[RightPanelChamberRowViewModel, ...],
        *,
        total_seconds: int,
        gcsim_status: RightPanelGcsimStatusViewModel,
    ) -> None:
        for row_index, row in enumerate(rows):
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
                if row.timer_editable and column in (1, 2):
                    cell = self._timer_cells.get((row_index, column))
                    if cell is not None:
                        if column == 1:
                            cell.set_model(
                                row.team1_time,
                                row.team1_seconds,
                                max_seconds=600,
                            )
                        else:
                            cell.set_model(
                                row.team2_time,
                                row.team2_seconds,
                                max_seconds=_remaining_seconds_from_time_text(
                                    row.team1_time
                                ),
                            )
                    continue
                label = self._row_labels.get((row_index, column))
                if label is not None:
                    label.setText(text)
                    if column == 3:
                        self._fact_dps_tooltips[(row_index, column)] = (
                            _set_custom_tooltip_text(
                                label,
                                self._fact_dps_tooltips.get((row_index, column)),
                                _fact_dps_tooltip_html(row.factual_team1_tooltip),
                            )
                        )
                    elif column == 4:
                        self._fact_dps_tooltips[(row_index, column)] = (
                            _set_custom_tooltip_text(
                                label,
                                self._fact_dps_tooltips.get((row_index, column)),
                                _fact_dps_tooltip_html(row.factual_team2_tooltip),
                            )
                        )
                    elif column == 5:
                        self._gcsim_tooltips[(row_index, column)] = (
                            _set_custom_tooltip_text(
                                label,
                                self._gcsim_tooltips.get((row_index, column)),
                                _gcsim_tooltip_html(row.sim_team1_tooltip),
                            )
                        )
                    elif column == 6:
                        self._gcsim_tooltips[(row_index, column)] = (
                            _set_custom_tooltip_text(
                                label,
                                self._gcsim_tooltips.get((row_index, column)),
                                _gcsim_tooltip_html(row.sim_team2_tooltip),
                            )
                        )
        if self._total_label is not None:
            self._total_label.setText(f"Total: {int(total_seconds)}s")
        if self._status_label is not None:
            self._status_label.setText(gcsim_status.status)
        if self._gcsim_button is not None:
            self._gcsim_button.setText(gcsim_status.button_label)


def _remaining_seconds_from_time_text(text: str) -> int:
    try:
        minutes_text, seconds_text = str(text).split(":", 1)
        return int(minutes_text) * 60 + int(seconds_text)
    except (TypeError, ValueError):
        return 600


def _fact_dps_tooltip_html(tooltip: FactDpsTooltipViewModel | None) -> str:
    if tooltip is None:
        return ""

    small_gap = "<div style='font-size:2px; line-height:2px;'>&nbsp;</div>"
    separator = "<span style='color:#b8aa86'>────────────────────────────</span><br>"
    parts = [
        "<qt>",
        f"<b>{html.escape(tooltip.title)}</b><br>",
    ]

    if tooltip.enemies:
        parts.append(f"<b>{html.escape(tr('right_panel.fact_dps.tooltip.enemies'))}</b><br>")
        current_wave: int | None = None
        for enemy in tooltip.enemies:
            if enemy.wave != current_wave:
                if current_wave is not None:
                    parts.append(small_gap)
                current_wave = enemy.wave
                parts.append(
                    f"<span style='color:#e8c474'>"
                    f"{html.escape(tr('right_panel.fact_dps.tooltip.wave', wave=enemy.wave))}"
                    f"</span><br>"
                )
            if enemy.cached_icon_path:
                path = Path(enemy.cached_icon_path).as_posix()
                parts.append(
                    f"<img src='{html.escape(path, quote=True)}' width='32' height='32'> "
                )
            name = html.escape(enemy.primary_display_name)
            level = (
                ""
                if enemy.display_level is None
                else f" Lv.{int(enemy.display_level)}"
            )
            parts.append(f"x{int(enemy.enemy_count)} {name}{level}")
            if enemy.selected_for_solo:
                parts.append(
                    " - "
                    + html.escape(tr("right_panel.fact_dps.tooltip.solo_target"))
                )
            if enemy.hp_used is not None:
                parts.append(
                    " - "
                    + html.escape(
                        tr(
                            "right_panel.fact_dps.tooltip.enemy_hp",
                            hp=f"{enemy.hp_used:,}",
                        )
                    )
                )
            else:
                parts.append(
                    " - "
                    + html.escape(tr("right_panel.fact_dps.tooltip.hp_unavailable"))
                )
            parts.append("<br>")

    parts.append(small_gap)
    parts.append(separator)
    parts.append(small_gap)
    parts.append(
        f"<b>{html.escape(tr('right_panel.fact_dps.tooltip.calculation'))}</b>: "
        +
        html.escape(
            tr(
                "right_panel.fact_dps.tooltip.multi_target",
                state=tooltip.hp_mode_label,
            )
        )
        + "<br>"
    )
    if tooltip.total_hp is not None:
        parts.append(
            html.escape(
                tr(
                    "right_panel.fact_dps.tooltip.hp_per_second",
                    hp=f"{tooltip.total_hp:,}",
                    seconds=int(tooltip.elapsed_seconds),
                )
            )
            + "<br>"
        )
    if tooltip.calculated_dps is not None:
        parts.append(
            html.escape(
                tr(
                    "right_panel.fact_dps.tooltip.dps",
                    dps=f"{tooltip.calculated_dps:,}",
                )
            )
            + "<br>"
        )
    if tooltip.unavailable_reason:
        parts.append(
            f"<span style='color:#e8c474'>"
            f"{html.escape(tr('right_panel.fact_dps.tooltip.reason', reason=tooltip.unavailable_reason))}"
            f"</span><br>"
        )

    parts.append(small_gap)
    parts.append(f"<b>{html.escape(tr('right_panel.fact_dps.tooltip.source'))}</b><br>")
    parts.append(
        html.escape(tr("right_panel.fact_dps.tooltip.composition_source")) + "<br>"
    )
    parts.append(
        html.escape(
            tr(
                "right_panel.fact_dps.tooltip.hp_source",
                source=tooltip.hp_source_label,
            )
        )
        + "<br>"
    )
    match_text = _fact_dps_match_confidence_text(tooltip)
    info_lines = _fact_dps_compact_info_lines(tooltip)
    if match_text or info_lines:
        parts.append(small_gap)
        parts.append(
            f"<b>{html.escape(tr('right_panel.fact_dps.tooltip.match_label'))}</b>"
        )
        if match_text:
            parts.append(" " + html.escape(match_text))
        parts.append("<br>")
        for info in info_lines:
            parts.append(html.escape(info) + "<br>")

    parts.append("</qt>")
    return "".join(parts)


def _gcsim_tooltip_html(tooltip: GcsimTooltipViewModel | None) -> str:
    if tooltip is None:
        return ""

    parts = [
        "<qt>",
        f"<b>{html.escape(tooltip.title)}</b><br>",
        _gcsim_tooltip_line("Status", tooltip.status),
        _gcsim_tooltip_line(
            "Sim clear time",
            _format_optional_number(tooltip.clear_time_seconds, suffix="s"),
        ),
        _gcsim_tooltip_line("Sim DPS mean", _format_optional_number(tooltip.dps_mean)),
        _gcsim_tooltip_line(
            "Avg total damage/run",
            _format_optional_number(tooltip.total_damage_mean),
        ),
        _gcsim_tooltip_line(
            "Scenario total HP",
            _format_optional_number(tooltip.scenario_total_hp),
        ),
        _gcsim_tooltip_line("Target mode", tooltip.target_mode),
        _gcsim_tooltip_line("Period start", tooltip.period_start),
        _gcsim_tooltip_line("Floor", str(tooltip.floor or "")),
        _gcsim_tooltip_line("Config path", tooltip.config_path),
        _gcsim_tooltip_line("Scenario path", tooltip.scenario_path),
        _gcsim_tooltip_line("Rotation hash", tooltip.rotation_hash),
    ]
    if tooltip.stale_reasons:
        parts.append("<br><b>Stale reasons</b><br>")
        parts.extend(
            f"- {html.escape(reason)}<br>"
            for reason in _capped_tooltip_items(tooltip.stale_reasons)
        )
    if tooltip.warnings:
        parts.append("<br><b>Warnings</b><br>")
        parts.extend(
            f"- {html.escape(warning)}<br>"
            for warning in _capped_tooltip_items(tooltip.warnings)
        )
    if tooltip.issues:
        parts.append("<br><b>Issues</b><br>")
        parts.extend(
            f"- {html.escape(issue)}<br>"
            for issue in _capped_tooltip_items(tooltip.issues)
        )
    if tooltip.notes:
        parts.append("<br><b>Notes</b><br>")
        parts.extend(
            f"- {html.escape(note)}<br>"
            for note in _capped_tooltip_items(tooltip.notes)
        )
    parts.append("</qt>")
    return "".join(parts)


def _gcsim_tooltip_line(label: str, value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return f"<b>{html.escape(label)}</b>: {html.escape(text)}<br>"


def _format_optional_number(value: object, *, suffix: str = "") -> str:
    if value in (None, ""):
        return ""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    return f"{number:g}{suffix}"


def _capped_tooltip_items(values: tuple[str, ...], *, limit: int = 6) -> tuple[str, ...]:
    if len(values) <= limit:
        return values
    return (*values[:limit], f"... +{len(values) - limit} more")


def _fact_dps_match_confidence_text(tooltip: FactDpsTooltipViewModel) -> str:
    confidences = {
        enemy.match_confidence
        for enemy in tooltip.enemies
        if enemy.match_confidence
    }
    if not confidences:
        return ""
    if len(confidences) == 1:
        confidence = next(iter(confidences))
        return _fact_dps_match_confidence_label(confidence)
    return tr("right_panel.fact_dps.tooltip.confidence_mixed")


def _fact_dps_match_method_label(method: str) -> str:
    key = {
        "strict_name": "right_panel.fact_dps.tooltip.match_method_strict",
        "variant_strip": "right_panel.fact_dps.tooltip.match_method_variant",
        "manual_alias": "right_panel.fact_dps.tooltip.match_method_alias",
        "context_unique_remaining": "right_panel.fact_dps.tooltip.match_method_context",
        "unmatched": "right_panel.fact_dps.tooltip.match_method_unmatched",
        "ambiguous": "right_panel.fact_dps.tooltip.match_method_ambiguous",
    }.get(method, "right_panel.fact_dps.tooltip.match_method_other")
    return tr(key)


def _fact_dps_match_confidence_label(confidence: str) -> str:
    key = {
        "high": "right_panel.fact_dps.tooltip.confidence_high",
        "medium": "right_panel.fact_dps.tooltip.confidence_medium",
        "low": "right_panel.fact_dps.tooltip.confidence_low",
        "none": "right_panel.fact_dps.tooltip.confidence_none",
    }.get(confidence, "right_panel.fact_dps.tooltip.confidence_none")
    return tr(key)


def _fact_dps_compact_info_lines(
    tooltip: FactDpsTooltipViewModel,
) -> tuple[str, ...]:
    lines: list[str] = []
    for enemy in tooltip.enemies:
        for warning in enemy.warnings:
            line = _fact_dps_enemy_warning_info_line(enemy, warning)
            if line and line not in lines:
                lines.append(line)
    for warning in tooltip.warnings:
        line = _fact_dps_source_warning_info_line(warning)
        if line and line not in lines:
            lines.append(line)
    if not lines:
        return ()
    visible = list(lines[:5])
    hidden_count = len(lines) - len(visible)
    if hidden_count > 0:
        visible.append(f"(+{hidden_count})")
    return tuple(visible)


def _fact_dps_enemy_warning_info_line(
    enemy: FactDpsEnemyTooltipViewModel,
    warning: str,
) -> str:
    lowered = warning.strip().lower()
    if not lowered:
        return ""
    enemy_name = enemy.primary_display_name
    if lowered == "selected_generic_stats_table_after_no_variant_heading_match":
        return tr(
            "right_panel.fact_dps.tooltip.info_generic_stats_table",
            enemy=enemy_name,
        )
    if lowered == "selected_from_multiple_level_hp_tables_by_heading":
        return tr(
            "right_panel.fact_dps.tooltip.info_matching_heading_table",
            enemy=enemy_name,
        )
    if lowered.startswith("multiple_generic_stats_tables_after_no_variant_heading_match"):
        return tr(
            "right_panel.fact_dps.tooltip.info_table_selection_ambiguous",
            enemy=enemy_name,
        )
    if lowered.startswith("multiple_level_hp_tables_ambiguous_heading_match"):
        return tr(
            "right_panel.fact_dps.tooltip.info_table_selection_ambiguous",
            enemy=enemy_name,
        )
    return ""


def _fact_dps_source_warning_info_line(warning: str) -> str:
    lowered = warning.strip().lower()
    if not lowered:
        return ""
    if lowered.startswith("multiple_generic_stats_tables_after_no_variant_heading_match"):
        return tr("right_panel.fact_dps.tooltip.info_some_table_ambiguous")
    if lowered.startswith("multiple_level_hp_tables_ambiguous_heading_match"):
        return tr("right_panel.fact_dps.tooltip.info_some_table_ambiguous")
    return ""


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

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        read_only: bool = False,
    ):
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
        self._details: RightPanelSelectedDetailsViewModel | None = None
        self._read_only = bool(read_only)
        self._build_stable_skeleton()

    def set_details(self, details: RightPanelSelectedDetailsViewModel) -> None:
        self._details = details
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

        self._bonus_strip = BonusSourceStripWidget(
            interactive=not self._read_only
        )
        self._bonus_strip.external_bonuses_toggled.connect(
            self.external_bonuses_toggled.emit
        )
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
        pixmap = _fit_pixmap(
            details.weapon_icon_path,
            QSize(50, 50),
            dpr=self._weapon_icon.devicePixelRatioF(),
        )
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

    def refresh_hidpi_pixmaps(self) -> None:
        if self._details is None or not self._details.has_selection:
            return
        self._set_weapon_summary(self._details)
        self._bonus_strip.refresh_hidpi_pixmaps()


class BonusSourceStripWidget(QFrame):
    external_bonuses_toggled = Signal(bool)

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        interactive: bool = True,
    ):
        super().__init__(parent)
        self.setObjectName("BonusSourceStrip")
        self._items_key: tuple[object, ...] | None = None
        self._items: tuple[RightPanelBonusSourceDisplayItem, ...] = ()
        self._external_bonuses_enabled = True
        self._interactive = bool(interactive)
        self.setCursor(
            Qt.CursorShape.PointingHandCursor
            if self._interactive
            else Qt.CursorShape.ArrowCursor
        )
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
        if self._interactive:
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
        self._items = tuple(items)
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
            empty = QLabel(tr("right_panel.bonus_tooltip.no_external_bonuses"))
            empty.setObjectName("BonusStripEmpty")
            empty.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            self._layout.addWidget(empty)
            self._layout.addStretch(1)
            return "rebuild_chips"
        for item in items:
            chip = BonusSourceChipWidget(item)
            if self._interactive:
                chip.installEventFilter(self)
            self._layout.addWidget(chip)
        self._layout.addStretch(1)
        return "rebuild_chips"

    def refresh_hidpi_pixmaps(self) -> None:
        self._items_key = None
        self.set_items(
            self._items,
            external_bonuses_enabled=self._external_bonuses_enabled,
        )

    def mouseReleaseEvent(self, event) -> None:
        if self._interactive and event.button() == Qt.MouseButton.LeftButton:
            self._toggle_external_bonuses()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _toggle_external_bonuses(self) -> None:
        if not self._interactive:
            return
        self.external_bonuses_toggled.emit(not self._external_bonuses_enabled)

    def _set_external_bonuses_enabled(self, enabled: bool) -> None:
        self._external_bonuses_enabled = bool(enabled)
        self.setProperty("active", self._external_bonuses_enabled)
        self.style().unpolish(self)
        self.style().polish(self)

    def eventFilter(self, watched, event) -> bool:
        if self._interactive and event.type() == QEvent.Type.MouseButtonRelease:
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
                tuple(item.tooltip_effects),
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
        self._item = item
        self.setObjectName("BonusSourceChip")
        self.setProperty("disabled", not item.applied)
        self.setFixedHeight(BONUS_SOURCE_CHIP_HEIGHT)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 0, 4, 0)
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
            _bonus_source_icon_pixmap(
                item.icon_path,
                QSize(22, 22),
                dpr=self.devicePixelRatioF(),
            )
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
            member_icon.setFixedSize(BONUS_MEMBER_ICON_SIZE, BONUS_MEMBER_ICON_SIZE)
            member_pixmap = (
                _bonus_member_side_icon_pixmap(
                    path,
                    QSize(BONUS_MEMBER_ICON_SIZE, BONUS_MEMBER_ICON_SIZE),
                    dpr=self.devicePixelRatioF(),
                )
                if path
                else None
            )
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
    effect_lines = _unique_text_lines(tuple(item.tooltip_effects or item.short_effects))
    if effect_lines:
        rows.append(
            f"<b>{html.escape(tr('right_panel.bonus_tooltip.effects'))}:</b><br>"
            + "<br>".join(f"- {html.escape(line)}" for line in effect_lines)
        )
    if not item.applied and item.not_applied_reason:
        rows.append(
            f"<span style='color:#f09c9c;'>{html.escape(item.not_applied_reason)}</span>"
        )
    if item.tooltip_body:
        body_lines = _filtered_bonus_tooltip_body_lines(
            _clean_set_bonus_description(item.tooltip_body),
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
    title_key = _tooltip_compare_key(title)
    effect_keys = {_tooltip_compare_key(effect) for effect in effects}
    effects_heading_keys = {
        "effects",
        _tooltip_compare_key(tr("right_panel.bonus_tooltip.effects")),
    }
    result: list[str] = []
    seen: set[str] = set()
    for raw_line in str(body or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        key = _tooltip_compare_key(line)
        if key == title_key or key in effect_keys or key in seen:
            continue
        if key in effects_heading_keys:
            continue
        result.append(line)
        seen.add(key)
    return tuple(result)


def _tooltip_compare_key(value: str) -> str:
    return str(value or "").strip().rstrip(".;:").strip().casefold()


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






def _bonus_source_icon_pixmap(
    path: str,
    size: QSize,
    *,
    dpr: float = 1.0,
) -> QPixmap | None:
    if not path:
        return None
    resolved = _resolve_pixmap_path(path)
    try:
        stat = resolved.stat()
        key = (
            str(resolved),
            int(size.width()),
            int(size.height()),
            int(round(effective_pixmap_dpr(dpr) * 1000)),
            int(stat.st_mtime_ns),
            int(stat.st_size),
        )
    except OSError:
        key = (
            str(path),
            int(size.width()),
            int(size.height()),
            int(round(effective_pixmap_dpr(dpr) * 1000)),
            0,
            0,
        )

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
        dpr=dpr,
    )
    _BONUS_SOURCE_ICON_PIXMAP_CACHE[key] = QPixmap(pixmap)
    return pixmap




def _bonus_member_side_icon_pixmap(
    path: str,
    size: QSize,
    *,
    dpr: float = 1.0,
) -> QPixmap | None:
    if not path:
        return None
    resolved = _resolve_pixmap_path(path)
    try:
        stat = resolved.stat()
        key = (
            str(resolved),
            int(size.width()),
            int(size.height()),
            int(round(effective_pixmap_dpr(dpr) * 1000)),
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
            int(round(effective_pixmap_dpr(dpr) * 1000)),
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

    effective_dpr = effective_pixmap_dpr(dpr)
    target_height = max(1, int(round(size.height() * BONUS_MEMBER_ICON_SCALE / 100)))
    physical_target_height = max(1, int(round(target_height * effective_dpr)))
    scaled = source.scaledToHeight(
        physical_target_height,
        Qt.TransformationMode.SmoothTransformation,
    )
    scaled.setDevicePixelRatio(effective_dpr)
    scaled_size = logical_pixmap_size(scaled)
    canvas = make_hidpi_canvas(size, effective_dpr)
    painter = QPainter(canvas)
    x = (size.width() - scaled_size.width()) // 2
    y = size.height() - scaled_size.height() - BONUS_MEMBER_ICON_BOTTOM_PADDING
    icon_rect = QRect(x, y, scaled_size.width(), scaled_size.height())
    badge_size = owner_badge_size_for_icon(icon_rect.size())
    badge_rect = owner_badge_rect_for_icon_rect(icon_rect, badge_size)
    if OWNER_BADGE_TRACE:
        print(
            "[OWNER_BADGE_TRACE] "
            "surface=right_panel_bonus_member "
            f"canvas={size.width()}x{size.height()} "
            f"source={str(resolved)!r} "
            f"owner_scaled={scaled.width()}x{scaled.height()} "
            f"owner_target={_trace_rect(icon_rect)} "
            f"badge_size={badge_size.width()}x{badge_size.height()} "
            f"badge_rect={_trace_rect(badge_rect)} "
            "computed_from=owner_icon_rect"
        )
    painter.drawPixmap(
        badge_rect,
        make_owner_icon_badge_background(badge_size, dpr=effective_dpr),
    )
    painter.drawPixmap(x, y, scaled)
    painter.end()
    _BONUS_MEMBER_SIDE_ICON_PIXMAP_CACHE[key] = QPixmap(canvas)
    return canvas




def right_panel_stylesheet() -> str:
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
    #SlotCard[dragHover="true"], #SlotCardSelected[dragHover="true"] {
        border-color: #7cc7ff;
        background: #334052;
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
    #TableHeader, #TableSubHeader {
        color: #98c9bf;
        font-size: 10px;
        font-weight: 800;
    }
    #TableSubHeader {
        color: #7ea99f;
        font-size: 9px;
    }
    #TableCell, #FactDpsCell, #TableCellPrimary, #ChamberBadge, #TimerTableCell {
        min-height: 22px;
        border-radius: 4px;
        background: #15181d;
        color: #dce3e7;
        padding: 1px 3px;
        font-family: Consolas, "Courier New", monospace;
    }
    #FactDpsCell {
        font-size: 11px;
        font-weight: 800;
    }
    #TimerTableCell {
        border: 1px solid #252c34;
        padding: 0px;
    }
    #TableCellPrimary, #ChamberBadge {
        color: #f1d486;
        font-weight: 800;
        font-family: Arial, sans-serif;
    }
    #ChamberBadge {
        border: 1px solid #343b44;
        background: #111419;
        padding: 0px;
    }
    #TimerEditorFrame {
        min-height: 18px;
        border-radius: 3px;
        border: 1px solid #303741;
        background: #101318;
    }
    #TimerSegmentEdit {
        min-height: 19px;
        border: 0px;
        background: transparent;
        color: #dce3e7;
        font-family: Consolas, "Courier New", monospace;
        font-size: 14px;
        font-weight: 700;
        padding: 0px;
    }
    #TimerSegmentEdit:focus {
        color: #ffffff;
        background: #202832;
    }
    #TimerSeparator, #TimerElapsed {
        color: #dce3e7;
        font-family: Consolas, "Courier New", monospace;
        font-size: 10px;
    }
    #TimerSeparator {
        font-size: 12px;
    }
    #TimerElapsed {
        color: #b9c4ca;
        font-size: 12px;
        font-weight: 800;
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
    """


# Deprecated compatibility names for old imports/tests.
RightPanelPrototypeWidget = RunRightPanelWidget
RightPanelTeamPrototypeWidget = RightPanelTeamCardWidget
RightPanelSlotPrototypeWidget = RightPanelSlotCardWidget

__all__ = [name for name in globals() if not name.startswith("__")]
