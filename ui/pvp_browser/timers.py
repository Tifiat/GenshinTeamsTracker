from __future__ import annotations

import html
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from localization import tr
from run_workspace.abyss.source_data import AbyssFloorSourceData
from ui.right_panel.pvp._shared import PVP_SEATS, PVP_TIMER_CHAMBERS, _parse_timer_text
from ui.utils.ui_palette import (
    UI_ACCENT_TEAM_1,
    UI_ACCENT_TEAM_2,
    UI_BG_BUTTON,
    UI_BG_INSET,
    UI_BG_PANEL,
    UI_BORDER_DEFAULT,
    UI_BORDER_PANEL,
    UI_STATE_DANGER,
    UI_STATE_SUCCESS,
    UI_TEXT_MUTED,
    UI_TEXT_PRIMARY,
    UI_TEXT_SECONDARY,
)


PVP_TIMERS_STYLE = f"""
QFrame#pvp_timers_workspace {{
    border: none;
    background: transparent;
}}
QFrame#pvp_timer_period,
QFrame#pvp_timer_chamber,
QFrame#pvp_timer_summary {{
    border: 1px solid {UI_BORDER_PANEL};
    border-radius: 7px;
    background: {UI_BG_PANEL};
}}
QLabel#pvp_timer_title {{
    color: {UI_TEXT_PRIMARY};
    font-size: 14px;
    font-weight: 900;
}}
QLabel#pvp_timer_chamber_title {{
    color: {UI_TEXT_PRIMARY};
    font-size: 13px;
    font-weight: 900;
}}
QLabel#pvp_timer_muted {{
    color: {UI_TEXT_MUTED};
    font-size: 11px;
}}
QLabel#pvp_timer_enemies {{
    color: {UI_TEXT_SECONDARY};
    background: {UI_BG_INSET};
    border: 1px solid {UI_BORDER_DEFAULT};
    border-radius: 5px;
    padding: 5px;
}}
QLineEdit#pvp_timer_input {{
    min-height: 28px;
    max-width: 94px;
    border: 1px solid {UI_BORDER_DEFAULT};
    border-radius: 5px;
    background: {UI_BG_INSET};
    color: {UI_TEXT_PRIMARY};
    font-family: Consolas, "Courier New", monospace;
    font-size: 13px;
    font-weight: 800;
    padding: 2px 7px;
}}
QLineEdit#pvp_timer_input[valid="true"] {{
    border-color: {UI_STATE_SUCCESS};
}}
QLineEdit#pvp_timer_input[invalid="true"] {{
    border-color: {UI_STATE_DANGER};
}}
QLineEdit#pvp_timer_input:read-only {{
    color: {UI_TEXT_MUTED};
    background: {UI_BG_BUTTON};
}}
QLabel#pvp_timer_team_1 {{ color: {UI_ACCENT_TEAM_1}; font-weight: 900; }}
QLabel#pvp_timer_team_2 {{ color: {UI_ACCENT_TEAM_2}; font-weight: 900; }}
QLabel#pvp_timer_result {{ color: {UI_TEXT_PRIMARY}; font-size: 13px; font-weight: 900; }}
QPushButton#pvp_timer_finalize {{
    min-height: 32px;
    border: 1px solid {UI_STATE_SUCCESS};
    border-radius: 6px;
    background: #24452d;
    color: {UI_TEXT_PRIMARY};
    font-weight: 900;
}}
QPushButton#pvp_timer_finalize:disabled {{
    border-color: {UI_BORDER_DEFAULT};
    background: {UI_BG_BUTTON};
    color: {UI_TEXT_MUTED};
}}
"""


class PvpTimersResultWidget(QFrame):
    timer_text_changed = Signal(str, int, str)
    finalize_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("pvp_timers_workspace")
        self.setStyleSheet(PVP_TIMERS_STYLE)
        self._timer_edits: dict[tuple[str, int], QLineEdit] = {}
        self._enemy_labels: dict[tuple[int, int], QLabel] = {}
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
            grid.setHorizontalSpacing(8)
            grid.setVerticalSpacing(5)

            chamber_label = QLabel(
                tr("app_shell.pvp.post.timer_chamber_title").format(chamber=chamber_id)
            )
            chamber_label.setObjectName("pvp_timer_chamber_title")
            grid.addWidget(chamber_label, 0, 0, 1, 2)

            for side in (1, 2):
                enemies = QLabel()
                enemies.setObjectName("pvp_timer_enemies")
                enemies.setTextFormat(Qt.TextFormat.RichText)
                enemies.setWordWrap(True)
                enemies.setMinimumHeight(42)
                self._enemy_labels[(chamber_index + 1, side)] = enemies
                grid.addWidget(enemies, side, 0, 1, 2)

            for column, seat in enumerate(PVP_SEATS, start=2):
                seat_label = QLabel(
                    tr("app_shell.pvp.post.timer_player_short").format(
                        player=1 if seat == "player_1" else 2,
                    )
                )
                seat_label.setObjectName(
                    "pvp_timer_team_1" if seat == "player_1" else "pvp_timer_team_2"
                )
                seat_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                grid.addWidget(seat_label, 0, column)

                edit = QLineEdit()
                edit.setObjectName("pvp_timer_input")
                edit.setPlaceholderText("00:00")
                edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
                edit.setClearButtonEnabled(True)
                edit.textChanged.connect(
                    lambda text, s=seat, i=chamber_index: self._on_timer_changed(s, i, text)
                )
                self._timer_edits[(seat, chamber_index)] = edit
                grid.addWidget(edit, 1, column, 2, 1)

            grid.setColumnStretch(0, 1)
            grid.setColumnStretch(1, 1)
            root.addWidget(frame)

        summary = QFrame()
        summary.setObjectName("pvp_timer_summary")
        summary_layout = QHBoxLayout(summary)
        summary_layout.setContentsMargins(10, 7, 10, 7)
        self.total_labels: dict[str, QLabel] = {}
        for seat in PVP_SEATS:
            label = QLabel()
            label.setObjectName(
                "pvp_timer_team_1" if seat == "player_1" else "pvp_timer_team_2"
            )
            self.total_labels[seat] = label
            summary_layout.addWidget(label)
        summary_layout.addStretch(1)
        self.result_label = QLabel()
        self.result_label.setObjectName("pvp_timer_result")
        summary_layout.addWidget(self.result_label)
        root.addWidget(summary)

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
            for (seat, index), edit in self._timer_edits.items():
                values = timer_texts.get(seat)
                text = str(values[index] or "") if isinstance(values, list) and index < len(values) else ""
                if edit.text() != text:
                    edit.setText(text)
                edit.setReadOnly(completed)
            self.title_label.setText(
                tr("app_shell.pvp.post.result_summary_title")
                if completed
                else tr("app_shell.pvp.post.timers_title")
            )
            self._set_source_data(source_data)
        finally:
            self._updating = False
        self._refresh_validation()
        self._refresh_summary(completed=completed, result=result or {})

    def timer_edit(self, seat: str, index: int) -> QLineEdit | None:
        return self._timer_edits.get((seat, index))

    def _on_timer_changed(self, seat: str, index: int, text: str) -> None:
        if self._updating:
            return
        self._refresh_validation()
        self._refresh_summary(completed=False, result={})
        self.timer_text_changed.emit(seat, index, text)

    def _refresh_validation(self) -> None:
        ready = True
        for edit in self._timer_edits.values():
            text = edit.text().strip()
            valid = _parse_timer_text(text) is not None
            edit.setProperty("valid", valid)
            edit.setProperty("invalid", bool(text) and not valid)
            edit.style().unpolish(edit)
            edit.style().polish(edit)
            ready = ready and valid
        self.finalize_button.setEnabled(ready)

    def _refresh_summary(self, *, completed: bool, result: Mapping[str, Any]) -> None:
        totals: dict[str, int | None] = {}
        for seat in PVP_SEATS:
            parsed = [
                _parse_timer_text(self._timer_edits[(seat, index)].text())
                for index in range(len(PVP_TIMER_CHAMBERS))
            ]
            total = sum(value for value in parsed if value is not None) if all(
                value is not None for value in parsed
            ) else None
            totals[seat] = total
            self.total_labels[seat].setText(
                tr("app_shell.pvp.post.timer_player_total").format(
                    player=1 if seat == "player_1" else 2,
                    total=_format_seconds(total),
                )
            )

        winner = str(result.get("winner_seat") or "") if completed else ""
        difference = int(result.get("seconds_difference") or 0) if completed else 0
        if not completed and totals["player_1"] is not None and totals["player_2"] is not None:
            difference = abs(int(totals["player_1"]) - int(totals["player_2"]))
            if totals["player_1"] < totals["player_2"]:
                winner = "player_1"
            elif totals["player_2"] < totals["player_1"]:
                winner = "player_2"
        if winner:
            self.result_label.setText(
                tr("app_shell.pvp.post.timer_leader").format(
                    player=1 if winner == "player_1" else 2,
                    difference=_format_seconds(difference),
                )
            )
        elif totals["player_1"] is not None and totals["player_2"] is not None:
            self.result_label.setText(tr("app_shell.pvp.post.timer_draw"))
        else:
            self.result_label.setText(tr("app_shell.pvp.post.timer_waiting"))
        self.finalize_button.setVisible(not completed)

    def _set_source_data(self, source_data: AbyssFloorSourceData | None) -> None:
        if source_data is None:
            self.period_label.setText(tr("app_shell.pvp.post.timer_period_unavailable"))
        else:
            end = source_data.period.end_date or ""
            self.period_label.setText(
                tr("app_shell.pvp.post.timer_period").format(
                    floor=source_data.floor,
                    start=source_data.period.start_date,
                    end=end,
                )
            )
        for chamber in range(1, len(PVP_TIMER_CHAMBERS) + 1):
            for side in (1, 2):
                label = self._enemy_labels[(chamber, side)]
                label.setText(_enemy_side_html(source_data, chamber=chamber, side=side))


def _enemy_side_html(
    source_data: AbyssFloorSourceData | None,
    *,
    chamber: int,
    side: int,
) -> str:
    side_title = tr("app_shell.pvp.post.timer_half_top" if side == 1 else "app_shell.pvp.post.timer_half_bottom")
    if source_data is None:
        return f"<b>{html.escape(side_title)}</b> <span style='color:#87919b'>{html.escape(tr('app_shell.pvp.post.timer_monsters_unavailable'))}</span>"
    rows = [
        row
        for row in source_data.enemy_rows
        if row.chamber == chamber and row.side == side
    ]
    if not rows:
        return f"<b>{html.escape(side_title)}</b> <span style='color:#87919b'>{html.escape(tr('app_shell.pvp.post.timer_monsters_unavailable'))}</span>"
    parts = [f"<b>{html.escape(side_title)}</b>&nbsp;&nbsp;"]
    current_wave: int | None = None
    for row in rows:
        if current_wave is not None and row.wave != current_wave:
            parts.append("&nbsp;|&nbsp;")
        current_wave = row.wave
        if row.cached_icon_path and Path(row.cached_icon_path).is_file():
            path = Path(row.cached_icon_path).as_posix()
            parts.append(f"<img src='{html.escape(path, quote=True)}' width='28' height='28'>&nbsp;")
        parts.append(
            f"x{int(row.enemy_count)} {html.escape(row.primary_display_name)}&nbsp;&nbsp;"
        )
    return "".join(parts)


def _format_seconds(seconds: int | None) -> str:
    if seconds is None:
        return "--:--"
    minutes, remainder = divmod(max(0, int(seconds)), 60)
    return f"{minutes:02d}:{remainder:02d}"


__all__ = ["PvpTimersResultWidget"]
