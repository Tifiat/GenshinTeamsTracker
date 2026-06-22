from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from localization import tr
from run_workspace.abyss.source_data import (
    AbyssChamberSideSourceData,
    AbyssEnemySourceRow,
    AbyssFloorSourceData,
)
from run_workspace.models import (
    ABYSS_CHAMBER_START_SECONDS,
    ABYSS_TIMER_EDIT_MIN_SECONDS,
)
from ui.right_panel.common.timer_input import CompactTimerInputWidget
from ui.right_panel.pvp._shared import (
    PVP_SEATS,
    PVP_TIMER_CHAMBERS,
    _parse_pvp_remaining_timer_text,
)
from ui.utils.hidpi_pixmap import load_hidpi_pixmap
from ui.utils.ui_palette import (
    UI_BG_BUTTON,
    UI_BG_BUTTON_CHECKED,
    UI_BG_BUTTON_HOVER,
    UI_BG_INSET,
    UI_BG_PANEL,
    UI_BORDER_DEFAULT,
    UI_BORDER_PANEL,
    UI_STATE_DANGER,
    UI_STATE_SUCCESS,
    UI_TEXT_MUTED,
    UI_TEXT_ON_ACCENT,
    UI_TEXT_PRIMARY,
    UI_TEXT_SECONDARY,
)
from ui.utils.pvp_colors import pvp_player_color


PVP_TIMER_HP_COLUMN_MIN_WIDTH = 126
PVP_TIMER_HP_COLUMN_WIDTH = 210
PVP_TIMER_INPUT_COLUMN_MIN_WIDTH = 128
PVP_TIMER_INPUT_COLUMN_WIDTH = 220
PVP_TIMER_MONSTERS_COLUMN_MIN_WIDTH = 74


def pvp_timers_style() -> str:
    player_1_color = pvp_player_color("player_1")
    player_2_color = pvp_player_color("player_2")
    return f"""
QFrame#pvp_timers_workspace {{ border: none; background: transparent; }}
QFrame#pvp_timer_period,
QFrame#pvp_timer_chamber,
QFrame#pvp_timer_scoreboard {{
    border: 1px solid {UI_BORDER_PANEL};
    border-radius: 7px;
    background: {UI_BG_PANEL};
}}
QLabel#pvp_timer_title {{ color: {UI_TEXT_PRIMARY}; font-size: 14px; font-weight: 900; }}
QLabel#pvp_timer_chamber_title {{ color: {UI_TEXT_PRIMARY}; font-size: 13px; font-weight: 900; }}
QLabel#pvp_timer_muted {{ color: {UI_TEXT_MUTED}; font-size: 11px; }}
QFrame#pvp_timer_side {{
    border: 1px solid {UI_BORDER_DEFAULT};
    border-radius: 5px;
    background: {UI_BG_INSET};
}}
QLabel#pvp_timer_side_title {{ color: {UI_TEXT_PRIMARY}; font-size: 11px; font-weight: 900; }}
QWidget#pvp_timer_waves {{ background: transparent; border: none; }}
QWidget#pvp_timer_wave {{ background: transparent; border: none; }}
QLabel#pvp_timer_wave_title {{ color: {UI_TEXT_MUTED}; font-size: 10px; font-weight: 800; }}
QLabel#pvp_timer_enemy_name {{ color: {UI_TEXT_SECONDARY}; font-size: 11px; }}
QFrame#pvp_timer_hp {{
    border: 1px solid {UI_BORDER_DEFAULT};
    border-radius: 5px;
    background: {UI_BG_BUTTON};
}}
QLabel#pvp_timer_hp_title {{ color: {UI_TEXT_MUTED}; font-size: 11px; font-weight: 800; }}
QLabel#pvp_timer_hp_value {{ color: {UI_TEXT_PRIMARY}; font-size: 12px; font-weight: 900; }}
QLabel#pvp_timer_player_1 {{ color: {player_1_color}; font-weight: 900; }}
QLabel#pvp_timer_player_2 {{ color: {player_2_color}; font-weight: 900; }}
QWidget#pvp_timer_input_column {{
    background: transparent;
    border: none;
}}
#TimerEditorFrame {{
    min-height: 38px;
    border-radius: 5px;
    border: 1px solid {UI_BORDER_DEFAULT};
    background: {UI_BG_INSET};
}}
#TimerEditorFrame[ready="true"] {{ border-color: {UI_STATE_SUCCESS}; }}
#TimerSegmentEdit {{
    min-height: 27px;
    border: 0px;
    background: transparent;
    color: {UI_TEXT_PRIMARY};
    font-family: Consolas, "Courier New", monospace;
    font-size: 20px;
    font-weight: 800;
    padding: 0px;
}}
#TimerSegmentEdit:focus {{ color: {UI_TEXT_ON_ACCENT}; background: {UI_BG_BUTTON_HOVER}; }}
#TimerSegmentEdit:read-only {{ color: {UI_TEXT_MUTED}; background: {UI_BG_BUTTON}; }}
#TimerSeparator {{ color: {UI_TEXT_PRIMARY}; font-size: 18px; font-weight: 900; }}
QLabel#pvp_timer_score_player_1,
QLabel#pvp_timer_score_player_2 {{ font-size: 17px; font-weight: 900; }}
QLabel#pvp_timer_score_player_1 {{ color: {player_1_color}; }}
QLabel#pvp_timer_score_player_2 {{ color: {player_2_color}; }}
QLabel#pvp_timer_chevron {{ font-size: 19px; font-weight: 900; }}
QLabel#pvp_timer_chevron[outcome="winner"] {{ color: {UI_STATE_SUCCESS}; }}
QLabel#pvp_timer_chevron[outcome="loser"] {{ color: {UI_STATE_DANGER}; }}
QLabel#pvp_timer_chevron[outcome="neutral"] {{ color: {UI_TEXT_MUTED}; }}
QLabel#pvp_timer_difference {{
    min-width: 64px;
    border: 1px solid {UI_BORDER_DEFAULT};
    border-radius: 5px;
    background: {UI_BG_INSET};
    color: {UI_TEXT_PRIMARY};
    font-family: Consolas, "Courier New", monospace;
    font-size: 16px;
    font-weight: 900;
    padding: 4px 10px;
}}
QLabel#pvp_timer_difference[winnerSeat="player_1"] {{
    border-color: {player_1_color};
    color: {player_1_color};
}}
QLabel#pvp_timer_difference[winnerSeat="player_2"] {{
    border-color: {player_2_color};
    color: {player_2_color};
}}
QFrame#pvp_timer_dps_table {{
    border: 1px solid {UI_BORDER_DEFAULT};
    border-radius: 5px;
    background: {UI_BG_INSET};
}}
QLabel#pvp_timer_dps_header {{
    color: {UI_TEXT_MUTED};
    font-size: 11px;
    font-weight: 900;
}}
QLabel#pvp_timer_dps_player {{ font-size: 12px; font-weight: 900; }}
QLabel#pvp_timer_dps_value {{
    color: {UI_TEXT_PRIMARY};
    font-size: 13px;
    font-weight: 900;
}}
QPushButton#pvp_timer_finalize {{
    min-height: 32px;
    border: 1px solid {UI_STATE_SUCCESS};
    border-radius: 6px;
    background: {UI_BG_BUTTON_CHECKED};
    color: {UI_TEXT_PRIMARY};
    font-weight: 900;
}}
QPushButton#pvp_timer_finalize:disabled {{
    border-color: {UI_BORDER_DEFAULT};
    background: {UI_BG_BUTTON};
    color: {UI_TEXT_MUTED};
}}
"""


class PvpChamberSideWidget(QFrame):
    def __init__(self, *, chamber: int, side: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.chamber = chamber
        self.side = side
        self.setObjectName("pvp_timer_side")
        self.setMinimumWidth(PVP_TIMER_MONSTERS_COLUMN_MIN_WIDTH)
        self.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Preferred,
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(7, 5, 7, 5)
        layout.setSpacing(8)
        self.side_label = QLabel()
        self.side_label.setObjectName("pvp_timer_side_title")
        self.side_label.setFixedWidth(42)
        layout.addWidget(self.side_label)

        self.waves_widget = QWidget()
        self.waves_widget.setObjectName("pvp_timer_waves")
        self.waves_widget.setMinimumWidth(0)
        self.waves_widget.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Preferred,
        )
        self.waves_layout = QVBoxLayout(self.waves_widget)
        self.waves_layout.setContentsMargins(0, 0, 0, 0)
        self.waves_layout.setSpacing(3)
        layout.addWidget(self.waves_widget, 1)

    def set_source_data(self, source_data: AbyssFloorSourceData | None) -> None:
        self.side_label.setText(
            tr(
                "app_shell.pvp.post.timer_half_top"
                if self.side == 1
                else "app_shell.pvp.post.timer_half_bottom"
            )
        )
        rows = () if source_data is None else tuple(
            row
            for row in source_data.enemy_rows
            if row.chamber == self.chamber and row.side == self.side
        )
        _clear_layout(self.waves_layout)
        if not rows:
            unavailable = QLabel(tr("app_shell.pvp.post.timer_monsters_unavailable"))
            unavailable.setObjectName("pvp_timer_muted")
            unavailable.setWordWrap(True)
            unavailable.setMinimumWidth(0)
            unavailable.setSizePolicy(
                QSizePolicy.Policy.Ignored,
                QSizePolicy.Policy.Preferred,
            )
            self.waves_layout.addWidget(unavailable)
        else:
            rows_by_wave: dict[int, list[AbyssEnemySourceRow]] = defaultdict(list)
            for row in rows:
                rows_by_wave[row.wave].append(row)
            for wave, wave_rows in sorted(rows_by_wave.items()):
                self.waves_layout.addWidget(_build_wave_widget(wave, wave_rows))



class PvpHpSummaryWidget(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("pvp_timer_hp")
        self.setMinimumWidth(PVP_TIMER_HP_COLUMN_MIN_WIDTH)
        self.setMaximumWidth(PVP_TIMER_HP_COLUMN_WIDTH)
        self.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Preferred,
        )
        layout = QGridLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setHorizontalSpacing(10)
        layout.setVerticalSpacing(3)
        self.solo_title = QLabel(tr("app_shell.pvp.post.timer_hp_solo"))
        self.solo_title.setObjectName("pvp_timer_hp_title")
        self.solo_value = QLabel("-")
        self.solo_value.setObjectName("pvp_timer_hp_value")
        self.solo_value.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.multi_title = QLabel(tr("app_shell.pvp.post.timer_hp_multi"))
        self.multi_title.setObjectName("pvp_timer_hp_title")
        self.multi_value = QLabel("-")
        self.multi_value.setObjectName("pvp_timer_hp_value")
        self.multi_value.setAlignment(Qt.AlignmentFlag.AlignRight)
        layout.addWidget(self.solo_title, 0, 0)
        layout.addWidget(self.solo_value, 0, 1)
        layout.addWidget(self.multi_title, 1, 0)
        layout.addWidget(self.multi_value, 1, 1)

    def set_values(self, *, solo_hp: int | None, multi_hp: int | None) -> None:
        self.solo_value.setText(_format_hp(solo_hp))
        self.multi_value.setText(_format_hp(multi_hp))


class PvpTimersResultWidget(QFrame):
    timer_text_changed = Signal(str, int, str)
    finalize_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("pvp_timers_workspace")
        self.setStyleSheet(pvp_timers_style())
        self.setMinimumWidth(0)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        self._timer_inputs: dict[tuple[str, int], CompactTimerInputWidget] = {}
        self._timer_touched: dict[tuple[str, int], bool] = {}
        self._side_widgets: dict[tuple[int, int], PvpChamberSideWidget] = {}
        self._hp_widgets: dict[tuple[int, int], PvpHpSummaryWidget] = {}
        self._source_data: AbyssFloorSourceData | None = None
        self._updating = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        period_frame = QFrame()
        period_frame.setObjectName("pvp_timer_period")
        period_layout = QHBoxLayout(period_frame)
        period_layout.setContentsMargins(10, 7, 10, 7)
        self.title_label = QLabel()
        self.title_label.setObjectName("pvp_timer_title")
        period_layout.addWidget(self.title_label)
        period_layout.addStretch(1)
        self.period_label = QLabel()
        self.period_label.setObjectName("pvp_timer_muted")
        period_layout.addWidget(self.period_label)
        root.addWidget(period_frame)

        for chamber_index, chamber_id in enumerate(PVP_TIMER_CHAMBERS):
            frame = QFrame()
            frame.setObjectName("pvp_timer_chamber")
            grid = QGridLayout(frame)
            grid.setContentsMargins(10, 8, 10, 8)
            grid.setHorizontalSpacing(10)
            grid.setVerticalSpacing(5)

            chamber_label = QLabel(
                tr("app_shell.pvp.post.timer_chamber_title").format(chamber=chamber_id)
            )
            chamber_label.setObjectName("pvp_timer_chamber_title")
            grid.addWidget(chamber_label, 0, 0, 1, 3)

            timer_column = QWidget()
            timer_column.setObjectName("pvp_timer_input_column")
            timer_column.setMinimumWidth(PVP_TIMER_INPUT_COLUMN_MIN_WIDTH)
            timer_column.setMaximumWidth(PVP_TIMER_INPUT_COLUMN_WIDTH)
            timer_column.setSizePolicy(
                QSizePolicy.Policy.Preferred,
                QSizePolicy.Policy.Fixed,
            )
            timer_layout = QVBoxLayout(timer_column)
            timer_layout.setContentsMargins(0, 0, 0, 0)
            timer_layout.setSpacing(6)
            timer_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
            for seat in PVP_SEATS:
                seat_label = QLabel(
                    tr("app_shell.pvp.post.timer_player_short").format(
                        player=1 if seat == "player_1" else 2,
                    )
                )
                seat_label.setObjectName(
                    "pvp_timer_player_1" if seat == "player_1" else "pvp_timer_player_2"
                )
                seat_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                timer_layout.addWidget(seat_label)

                timer = CompactTimerInputWidget(
                    minimum_seconds=ABYSS_TIMER_EDIT_MIN_SECONDS,
                    maximum_seconds=ABYSS_CHAMBER_START_SECONDS,
                    initial_seconds=ABYSS_CHAMBER_START_SECONDS,
                    wide=True,
                )
                timer.setMinimumWidth(PVP_TIMER_INPUT_COLUMN_MIN_WIDTH)
                timer.setMaximumWidth(PVP_TIMER_INPUT_COLUMN_WIDTH)
                timer.seconds_changed.connect(
                    lambda seconds, s=seat, i=chamber_index: self._on_timer_changed(
                        s, i, seconds
                    )
                )
                self._timer_inputs[(seat, chamber_index)] = timer
                self._timer_touched[(seat, chamber_index)] = False
                timer_layout.addWidget(timer)

            for side in (1, 2):
                side_widget = PvpChamberSideWidget(
                    chamber=chamber_index + 1,
                    side=side,
                )
                self._side_widgets[(chamber_index + 1, side)] = side_widget
                grid.addWidget(side_widget, side, 0)
                hp_widget = PvpHpSummaryWidget()
                self._hp_widgets[(chamber_index + 1, side)] = hp_widget
                grid.addWidget(hp_widget, side, 1)

            grid.addWidget(timer_column, 1, 2, 2, 1)
            grid.setColumnStretch(0, 1)
            grid.setColumnStretch(1, 0)
            grid.setColumnStretch(2, 0)
            grid.setColumnMinimumWidth(1, PVP_TIMER_HP_COLUMN_MIN_WIDTH)
            grid.setColumnMinimumWidth(2, PVP_TIMER_INPUT_COLUMN_MIN_WIDTH)
            root.addWidget(frame)

        scoreboard = QFrame()
        scoreboard.setObjectName("pvp_timer_scoreboard")
        scoreboard_layout = QVBoxLayout(scoreboard)
        scoreboard_layout.setContentsMargins(12, 8, 12, 8)
        scoreboard_layout.setSpacing(8)
        score_layout = QHBoxLayout()
        score_layout.setContentsMargins(0, 0, 0, 0)
        score_layout.setSpacing(6)
        self.total_labels: dict[str, QLabel] = {}
        self.total_labels["player_1"] = QLabel()
        self.total_labels["player_1"].setObjectName("pvp_timer_score_player_1")
        self.total_labels["player_1"].setWordWrap(True)
        self.total_labels["player_1"].setMinimumWidth(0)
        self.total_labels["player_1"].setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Preferred,
        )
        score_layout.addStretch(1)
        score_layout.addWidget(self.total_labels["player_1"])

        self.left_chevron = QLabel("·")
        self.left_chevron.setObjectName("pvp_timer_chevron")
        self.left_chevron.setAlignment(Qt.AlignmentFlag.AlignCenter)
        score_layout.addWidget(self.left_chevron)
        self.difference_label = QLabel(_format_score_seconds(None))
        self.difference_label.setObjectName("pvp_timer_difference")
        self.difference_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        score_layout.addWidget(self.difference_label)
        self.right_chevron = QLabel("·")
        self.right_chevron.setObjectName("pvp_timer_chevron")
        self.right_chevron.setAlignment(Qt.AlignmentFlag.AlignCenter)
        score_layout.addWidget(self.right_chevron)

        self.total_labels["player_2"] = QLabel()
        self.total_labels["player_2"].setObjectName("pvp_timer_score_player_2")
        self.total_labels["player_2"].setAlignment(Qt.AlignmentFlag.AlignRight)
        self.total_labels["player_2"].setWordWrap(True)
        self.total_labels["player_2"].setMinimumWidth(0)
        self.total_labels["player_2"].setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Preferred,
        )
        score_layout.addWidget(self.total_labels["player_2"])
        score_layout.addStretch(1)
        scoreboard_layout.addLayout(score_layout)

        self.dps_table_frame = QFrame()
        self.dps_table_frame.setObjectName("pvp_timer_dps_table")
        dps_layout = QGridLayout(self.dps_table_frame)
        dps_layout.setContentsMargins(10, 7, 10, 7)
        dps_layout.setHorizontalSpacing(8)
        dps_layout.setVerticalSpacing(4)
        self.dps_value_labels: dict[tuple[str, str], QLabel] = {}
        for column, text in enumerate(
            (
                "",
                tr("app_shell.pvp.post.timer_average_dps_solo"),
                tr("app_shell.pvp.post.timer_average_dps_multi"),
            )
        ):
            header = QLabel(text)
            header.setObjectName("pvp_timer_dps_header")
            header.setWordWrap(True)
            header.setMinimumWidth(0)
            header.setSizePolicy(
                QSizePolicy.Policy.Ignored,
                QSizePolicy.Policy.Preferred,
            )
            header.setAlignment(
                Qt.AlignmentFlag.AlignRight if column else Qt.AlignmentFlag.AlignLeft
            )
            dps_layout.addWidget(header, 0, column)
        for row, seat in enumerate(PVP_SEATS, start=1):
            player_label = QLabel(
                tr("app_shell.pvp.post.timer_average_dps_title").format(
                    player=1 if seat == "player_1" else 2,
                )
            )
            player_label.setObjectName(
                "pvp_timer_player_1" if seat == "player_1" else "pvp_timer_player_2"
            )
            player_label.setProperty("seat", seat)
            player_label.setWordWrap(True)
            player_label.setMinimumWidth(0)
            player_label.setSizePolicy(
                QSizePolicy.Policy.Ignored,
                QSizePolicy.Policy.Preferred,
            )
            dps_layout.addWidget(player_label, row, 0)
            for column, mode in enumerate(("solo", "multi"), start=1):
                value = QLabel("-")
                value.setObjectName("pvp_timer_dps_value")
                value.setAlignment(Qt.AlignmentFlag.AlignRight)
                value.setMinimumWidth(0)
                value.setSizePolicy(
                    QSizePolicy.Policy.Ignored,
                    QSizePolicy.Policy.Preferred,
                )
                self.dps_value_labels[(seat, mode)] = value
                dps_layout.addWidget(value, row, column)
        dps_layout.setColumnStretch(0, 1)
        dps_layout.setColumnStretch(1, 0)
        dps_layout.setColumnStretch(2, 0)
        scoreboard_layout.addWidget(self.dps_table_frame)
        root.addWidget(scoreboard)

        self.finalize_button = QPushButton(tr("app_shell.pvp.post.finalize_result"))
        self.finalize_button.setObjectName("pvp_timer_finalize")
        self.finalize_button.clicked.connect(self.finalize_requested)
        root.addWidget(self.finalize_button)

    def set_state(
        self,
        *,
        completed: bool,
        timer_texts: Mapping[str, Any],
        result: Mapping[str, Any] | None,
        source_data: AbyssFloorSourceData | None,
    ) -> None:
        self._updating = True
        try:
            self._source_data = source_data
            for key, timer in self._timer_inputs.items():
                seat, index = key
                values = timer_texts.get(seat)
                text = str(values[index] or "") if isinstance(values, list) and index < len(values) else ""
                seconds = _parse_pvp_remaining_timer_text(text)
                self._timer_touched[key] = seconds is not None
                timer.set_seconds(
                    ABYSS_CHAMBER_START_SECONDS if seconds is None else seconds
                )
                timer.setReadOnly(completed)
            self.title_label.setText(
                tr("app_shell.pvp.post.result_summary_title")
                if completed
                else tr("app_shell.pvp.post.timers_title")
            )
            self._set_source_data(source_data)
        finally:
            self._updating = False
        self._refresh_validation()
        self._refresh_scoreboard_current(completed=completed, result=result or {})

    def timer_input(self, seat: str, index: int) -> CompactTimerInputWidget | None:
        return self._timer_inputs.get((seat, index))

    def refresh_player_colors(self) -> None:
        self.setStyleSheet(pvp_timers_style())
        self.update()

    def set_timer_seconds_for_test(self, seat: str, index: int, seconds: int) -> bool:
        timer = self.timer_input(seat, index)
        if timer is None:
            return False
        timer.set_seconds(seconds, emit=True)
        return True

    def _on_timer_changed(self, seat: str, index: int, seconds: int) -> None:
        if self._updating:
            return
        self._timer_touched[(seat, index)] = True
        self._refresh_validation()
        self._refresh_scoreboard_current(completed=False, result={})
        self.timer_text_changed.emit(seat, index, _format_seconds(seconds))

    def _refresh_validation(self) -> None:
        ready = all(self._timer_touched.values())
        for key, timer in self._timer_inputs.items():
            timer.setProperty("ready", self._timer_touched[key])
            timer.style().unpolish(timer)
            timer.style().polish(timer)
        self.finalize_button.setEnabled(ready)

    def _refresh_scoreboard_current(
        self,
        *,
        completed: bool,
        result: Mapping[str, Any],
    ) -> None:
        totals: dict[str, int] = {}
        for seat in PVP_SEATS:
            keys = [(seat, index) for index in range(len(PVP_TIMER_CHAMBERS))]
            total = sum(
                ABYSS_CHAMBER_START_SECONDS - self._timer_inputs[key].seconds_left
                for key in keys
            )
            if completed:
                result_totals = result.get("totals")
                if isinstance(result_totals, Mapping) and seat in result_totals:
                    total = max(0, int(result_totals[seat] or 0))
            totals[seat] = total
            self.total_labels[seat].setText(
                tr("app_shell.pvp.post.timer_player_total_seconds").format(
                    player=1 if seat == "player_1" else 2,
                    seconds=int(total),
                )
            )

        winner = str(result.get("winner_seat") or "") if completed else ""
        difference = int(result.get("seconds_difference") or 0) if completed else 0
        if not completed:
            difference = abs(totals["player_1"] - totals["player_2"])
            if totals["player_1"] < totals["player_2"]:
                winner = "player_1"
            elif totals["player_2"] < totals["player_1"]:
                winner = "player_2"

        if not winner:
            self._set_score_state_current(
                "neutral",
                "neutral",
                "-",
                "-",
                _format_score_seconds(0),
                "",
            )
        elif winner == "player_1":
            self._set_score_state_current(
                "winner",
                "loser",
                "\u25b2",
                "\u25bc",
                _format_score_seconds(difference),
                "player_1",
            )
        else:
            self._set_score_state_current(
                "loser",
                "winner",
                "\u25bc",
                "\u25b2",
                _format_score_seconds(difference),
                "player_2",
            )
        self._refresh_dps_summary(totals)
        self.finalize_button.setVisible(not completed)

    def _set_score_state_current(
        self,
        left_outcome: str,
        right_outcome: str,
        left_text: str,
        right_text: str,
        difference: str,
        winner_seat: str,
    ) -> None:
        self.left_chevron.setText(left_text)
        self.right_chevron.setText(right_text)
        self.difference_label.setText(difference)
        self.difference_label.setProperty("winnerSeat", winner_seat)
        self.difference_label.style().unpolish(self.difference_label)
        self.difference_label.style().polish(self.difference_label)
        for label, outcome in (
            (self.left_chevron, left_outcome),
            (self.right_chevron, right_outcome),
        ):
            label.setProperty("outcome", outcome)
            label.style().unpolish(label)
            label.style().polish(label)

    def _refresh_dps_summary(self, totals: Mapping[str, int]) -> None:
        solo_hp, multi_hp = _source_hp_totals(self._source_data)
        for seat in PVP_SEATS:
            total_seconds = max(0, int(totals.get(seat) or 0))
            solo_label = self.dps_value_labels.get((seat, "solo"))
            multi_label = self.dps_value_labels.get((seat, "multi"))
            if solo_label is not None:
                solo_label.setText(_format_dps(solo_hp, total_seconds))
            if multi_label is not None:
                multi_label.setText(_format_dps(multi_hp, total_seconds))

    def _set_source_data(self, source_data: AbyssFloorSourceData | None) -> None:
        if source_data is None:
            self.period_label.setText(tr("app_shell.pvp.post.timer_period_unavailable"))
        else:
            self.period_label.setText(
                tr("app_shell.pvp.post.timer_period").format(
                    floor=source_data.floor,
                    start=source_data.period.start_date,
                    end=source_data.period.end_date or "",
                )
            )
        for widget in self._side_widgets.values():
            widget.set_source_data(source_data)
        for (chamber, side), widget in self._hp_widgets.items():
            summary = _side_summary(source_data, chamber, side)
            widget.set_values(
                solo_hp=None if summary is None else summary.solo_target_hp,
                multi_hp=None if summary is None else summary.multi_target_hp,
            )


def _build_wave_widget(wave: int, rows: list[AbyssEnemySourceRow]) -> QWidget:
    widget = QWidget()
    widget.setObjectName("pvp_timer_wave")
    layout = QHBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(6)
    wave_label = QLabel(tr("app_shell.pvp.post.timer_wave").format(wave=wave))
    wave_label.setObjectName("pvp_timer_wave_title")
    wave_label.setFixedWidth(48)
    layout.addWidget(wave_label)
    for row in rows:
        icon = QLabel()
        icon.setFixedSize(30, 30)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if row.cached_icon_path and Path(row.cached_icon_path).is_file():
            result = load_hidpi_pixmap(
                row.cached_icon_path,
                QSize(30, 30),
                dpr=icon.devicePixelRatioF(),
                aspect_mode=Qt.AspectRatioMode.KeepAspectRatio,
                transform_mode=Qt.TransformationMode.SmoothTransformation,
                surface="pvp_timer_enemy",
            )
            if result.pixmap is not None:
                icon.setPixmap(result.pixmap)
        layout.addWidget(icon)
        name = QLabel(f"x{int(row.enemy_count)} {row.primary_display_name}")
        name.setObjectName("pvp_timer_enemy_name")
        name.setWordWrap(True)
        name.setMinimumWidth(0)
        name.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        layout.addWidget(name)
    layout.addStretch(1)
    return widget


def _side_summary(
    source_data: AbyssFloorSourceData | None,
    chamber: int,
    side: int,
) -> AbyssChamberSideSourceData | None:
    if source_data is None:
        return None
    return next(
        (
            summary
            for summary in source_data.side_summaries
            if summary.chamber == chamber and summary.side == side
        ),
        None,
    )


def _format_seconds(seconds: int | None) -> str:
    if seconds is None:
        return "--:--"
    minutes, remainder = divmod(max(0, int(seconds)), 60)
    return f"{minutes:02d}:{remainder:02d}"


def _format_score_seconds(seconds: int | None) -> str:
    return tr("app_shell.pvp.post.timer_seconds").format(
        seconds="--" if seconds is None else max(0, int(seconds))
    )


def _format_hp(value: int | None) -> str:
    return "—" if value is None else f"{int(value):,}".replace(",", " ")


def _source_hp_totals(source_data: AbyssFloorSourceData | None) -> tuple[int, int]:
    if source_data is None:
        return 0, 0
    solo = 0
    multi = 0
    for summary in source_data.side_summaries:
        solo += max(0, int(summary.solo_target_hp or 0))
        multi += max(0, int(summary.multi_target_hp or 0))
    return solo, multi


def _format_dps(hp: int, total_seconds: int) -> str:
    if hp <= 0 or total_seconds <= 0:
        return "-"
    return f"{int(round(hp / total_seconds)):,}".replace(",", " ")


def _clear_layout(layout: QVBoxLayout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.deleteLater()


__all__ = ["PvpChamberSideWidget", "PvpTimersResultWidget", "pvp_timers_style"]
