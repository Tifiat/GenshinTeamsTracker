from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

from localization import tr
from ui.right_panel.pvp._shared import *
from ui.right_panel.pvp.draft.assignment.target_slot import PvpPostDraftTargetSlotWidget


class PvpDraftRightPanel(QWidget):
    def __init__(
        self,
        workspace: PvpWorkspace,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.workspace = workspace
        self.setObjectName("RightPanelPrototypeContent")
        self.setStyleSheet(PVP_DECKS_RIGHT_PANEL_STYLE)

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        self.title_label = QLabel()
        self.title_label.setObjectName("SectionTitle")
        root.addWidget(self.title_label)

        self.empty_label = QLabel()
        self.empty_label.setObjectName("small_muted")
        self.empty_label.setWordWrap(True)
        root.addWidget(self.empty_label)

        self.match_frame = QFrame()
        self.match_frame.setObjectName("pvp_postdraft_match_panel")
        self.match_layout = QVBoxLayout(self.match_frame)
        self.match_layout.setContentsMargins(0, 0, 0, 0)
        self.match_layout.setSpacing(6)
        root.addWidget(self.match_frame, 1)
        self.target_zone_frames_by_seat: dict[str, QFrame] = {}
        self.team_slot_buttons_by_key: dict[tuple[str, int, int], PvpPostDraftTargetSlotWidget] = {}
        self.timer_inputs_by_key: dict[tuple[str, int], QLineEdit] = {}
        self.timer_total_labels_by_seat: dict[str, QLabel] = {}

        self.status_frame = QFrame()
        self.status_frame.setObjectName("pvp_deck_expanded_info")
        status_layout = QVBoxLayout(self.status_frame)
        status_layout.setContentsMargins(8, 8, 8, 8)
        status_layout.setSpacing(5)
        self.status_labels: list[QLabel] = []
        for _index in range(5):
            label = QLabel()
            label.setObjectName("pvp_deck_info_line")
            label.setWordWrap(True)
            status_layout.addWidget(label)
            self.status_labels.append(label)
        root.addWidget(self.status_frame)

        self.stage_button = QPushButton()
        self.stage_button.setObjectName("pvp_primary_button")
        self.stage_button.clicked.connect(self._on_stage_button_clicked)
        root.addWidget(self.stage_button)

        self.result_zone_frames: dict[tuple[str, str], QFrame] = {}
        self.result_zone_title_labels: dict[tuple[str, str], QLabel] = {}
        self.result_zone_value_labels: dict[tuple[str, str], QLabel] = {}
        for seat in ("player_1", "player_2"):
            for zone in ("picked", "banned"):
                frame = QFrame()
                frame.setObjectName("pvp_draft_result_zone")
                frame_layout = QVBoxLayout(frame)
                frame_layout.setContentsMargins(8, 7, 8, 7)
                frame_layout.setSpacing(3)
                title = QLabel()
                title.setObjectName("pvp_draft_result_title")
                frame_layout.addWidget(title)
                value = QLabel()
                value.setObjectName(
                    "pvp_draft_result_picks"
                    if zone == "picked"
                    else "pvp_draft_result_bans"
                )
                value.setWordWrap(True)
                frame_layout.addWidget(value)
                root.addWidget(frame)
                key = (seat, zone)
                self.result_zone_frames[key] = frame
                self.result_zone_title_labels[key] = title
                self.result_zone_value_labels[key] = value

        self.log_title_label = QLabel()
        self.log_title_label.setObjectName("pvp_deck_info_line")
        root.addWidget(self.log_title_label)

        self.log_labels: list[QLabel] = []
        for _index in range(5):
            label = QLabel()
            label.setObjectName("small_muted")
            label.setWordWrap(True)
            root.addWidget(label)
            self.log_labels.append(label)

        self.clear_button = QPushButton()
        self.clear_button.setObjectName("pvp_secondary_button")
        self.clear_button.clicked.connect(self.workspace.clear_active_draft)
        root.addWidget(self.clear_button)

        self.play_button = QPushButton()
        self.play_button.setObjectName("pvp_secondary_button")
        self.play_button.clicked.connect(lambda: self.workspace.set_page(PVP_PAGE_PLAY))
        root.addWidget(self.play_button)

        self.message_label = QLabel()
        self.message_label.setObjectName("small_muted")
        self.message_label.setWordWrap(True)
        root.addWidget(self.message_label)

        self.workspace.state_changed.connect(self.refresh)
        self.workspace.active_draft_changed.connect(self.refresh)
        self.retranslate_ui()
        self.refresh()

    def refresh(self) -> None:
        session = self.workspace.active_draft_session
        has_session = session is not None
        self.empty_label.setVisible(not has_session)
        self.match_frame.setVisible(False)
        self.status_frame.setVisible(has_session)
        self.log_title_label.setVisible(has_session)
        self.clear_button.setVisible(has_session)
        self.clear_button.setEnabled(has_session)
        self.stage_button.setVisible(has_session)
        self.play_button.setVisible(True)
        self.message_label.setText(self.workspace.last_draft_status())
        self.message_label.setVisible(bool(self.message_label.text()))

        if session is None:
            _clear_layout(self.match_layout)
            self._clear_match_registries()
            for label in (*self.status_labels, *self.log_labels):
                label.clear()
                label.setVisible(False)
            for frame in self.result_zone_frames.values():
                frame.setVisible(False)
            self.stage_button.setVisible(False)
            return

        board = session.board_dict()
        stage = self.workspace.draft_stage
        post_draft_stage = _is_post_draft_stage(stage)
        if post_draft_stage:
            self._rebuild_match_panel(board, stage)
        else:
            _clear_layout(self.match_layout)
            self._clear_match_registries()
        self.match_frame.setVisible(post_draft_stage)
        status_lines = _draft_panel_status_lines(board, stage=stage, workspace=self.workspace)
        for index, label in enumerate(self.status_labels):
            text = status_lines[index] if index < len(status_lines) else ""
            label.setText(text)
            label.setVisible(bool(text))

        self._refresh_stage_button(board, stage)

        show_draft_summary = stage in {
            PVP_DRAFT_STAGE_DRAFT,
            PVP_DRAFT_STAGE_COMPLETED_RESULT,
        } and not post_draft_stage
        for key, frame in self.result_zone_frames.items():
            seat, zone = key
            self.result_zone_title_labels[key].setText(
                _draft_result_zone_title(seat, zone)
            )
            self.result_zone_value_labels[key].setText(
                _draft_result_zone_text(board, seat=seat, zone=zone)
            )
            frame.setVisible(show_draft_summary)

        log_lines = _draft_action_log_lines(board, limit=len(self.log_labels))
        self.log_title_label.setVisible(show_draft_summary)
        for index, label in enumerate(self.log_labels):
            text = log_lines[index] if index < len(log_lines) else ""
            label.setText(text)
            label.setVisible(show_draft_summary and bool(text))

    def retranslate_ui(self) -> None:
        self.title_label.setText(tr("app_shell.pvp.draft.title"))
        self.empty_label.setText(tr("app_shell.pvp.draft.no_active_body"))
        self.log_title_label.setText(tr("app_shell.pvp.draft.action_log_title"))
        self.clear_button.setText(tr("app_shell.pvp.draft.abandon"))
        self.play_button.setText(tr("app_shell.pvp.draft.back_to_play"))
        self.refresh()

    def _refresh_stage_button(self, board: Mapping[str, Any], stage: str) -> None:
        if stage == PVP_DRAFT_STAGE_DRAFT:
            self.stage_button.setText(tr("app_shell.pvp.post.continue_assignment"))
            self.stage_button.setVisible(_draft_is_complete(board))
            self.stage_button.setEnabled(_draft_is_complete(board))
            return
        if stage == PVP_DRAFT_STAGE_ASSIGNMENT:
            self.stage_button.setText(tr("app_shell.pvp.post.continue_weapons"))
            self.stage_button.setVisible(True)
            self.stage_button.setEnabled(self.workspace.assignment_ready())
            return
        if stage == PVP_DRAFT_STAGE_WEAPONS:
            self.stage_button.setText(tr("app_shell.pvp.post.continue_timers"))
            self.stage_button.setVisible(True)
            self.stage_button.setEnabled(self.workspace.weapons_ready())
            return
        if stage == PVP_DRAFT_STAGE_TIMERS_RESULTS:
            self.stage_button.setText(tr("app_shell.pvp.post.finalize_result"))
            self.stage_button.setVisible(True)
            self.stage_button.setEnabled(self.workspace.timers_ready())
            return
        self.stage_button.setVisible(False)

    def _on_stage_button_clicked(self) -> None:
        stage = self.workspace.draft_stage
        if stage == PVP_DRAFT_STAGE_DRAFT:
            self.workspace.continue_to_assignment()
        elif stage == PVP_DRAFT_STAGE_ASSIGNMENT:
            self.workspace.continue_to_weapons()
        elif stage == PVP_DRAFT_STAGE_WEAPONS:
            self.workspace.continue_to_timers()
        elif stage == PVP_DRAFT_STAGE_TIMERS_RESULTS:
            self.workspace.finalize_match_result()

    def _clear_match_registries(self) -> None:
        self.target_zone_frames_by_seat.clear()
        self.team_slot_buttons_by_key.clear()
        self.timer_inputs_by_key.clear()
        self.timer_total_labels_by_seat.clear()

    def _rebuild_match_panel(self, board: Mapping[str, Any], stage: str) -> None:
        _clear_layout(self.match_layout)
        self._clear_match_registries()
        session = self.workspace.active_draft_session
        if session is None:
            return
        for seat in PVP_SEATS:
            zone = QFrame()
            zone.setObjectName(_postdraft_target_object_name(seat))
            zone.setProperty("seat", seat)
            zone_layout = QVBoxLayout(zone)
            zone_layout.setContentsMargins(7, 7, 7, 7)
            zone_layout.setSpacing(5)
            self.target_zone_frames_by_seat[seat] = zone

            title = QLabel(_seat_label(seat))
            title.setObjectName("pvp_draft_result_title")
            zone_layout.addWidget(title)

            teams_row = QHBoxLayout()
            teams_row.setContentsMargins(0, 0, 0, 0)
            teams_row.setSpacing(5)
            for team_index in range(2):
                teams_row.addWidget(
                    self._build_target_team(board, session, stage, seat, team_index),
                    1,
                )
            zone_layout.addLayout(teams_row)

            self._add_timer_result_area(zone_layout, session, stage, seat)
            self.match_layout.addWidget(zone, 1)

    def _build_target_team(
        self,
        board: Mapping[str, Any],
        session: PvpActiveDraftSession,
        stage: str,
        seat: str,
        team_index: int,
    ) -> QFrame:
        frame = QFrame()
        frame.setObjectName("pvp-team-half")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(4)
        title = QLabel(
            tr("app_shell.pvp.post.team_title").format(index=team_index + 1)
        )
        title.setObjectName("small_muted")
        layout.addWidget(title)
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(3)
        grid.setVerticalSpacing(3)
        slots = _assignment_slots(self.workspace._draft_view_state(), seat)
        for slot_index in range(4):
            grid.addWidget(
                self._build_target_slot(
                    board,
                    session,
                    stage,
                    seat,
                    team_index,
                    slot_index,
                    slots[team_index][slot_index],
                ),
                slot_index // 2,
                slot_index % 2,
            )
        layout.addLayout(grid)
        return frame

    def _build_target_slot(
        self,
        board: Mapping[str, Any],
        session: PvpActiveDraftSession,
        stage: str,
        seat: str,
        team_index: int,
        slot_index: int,
        character_id: str | None,
    ) -> PvpPostDraftTargetSlotWidget:
        character_name = (
            _entry_display_name_for_id(board, character_id)
            if character_id
            else ""
        )
        portrait_path = _asset_image_path(
            self.workspace.draft_workspace._character_assets_by_id.get(
                character_id or "",
            )
        )
        stack_key = _weapon_assignment_map(self.workspace._draft_view_state(), seat).get(
            character_id or "",
            "",
        )
        weapon_name = _weapon_display_name(session, seat, stack_key)
        weapon_image_path = _asset_image_path(
            self.workspace.draft_workspace._weapon_assets_by_stack_key.get(stack_key)
        )
        slot = PvpPostDraftTargetSlotWidget()
        slot.configure(
            seat=seat,
            team_index=team_index,
            slot_index=slot_index,
            character_id=character_id or "",
            character_name=character_name,
            empty_label=tr("app_shell.pvp.post.empty_slot").format(index=slot_index + 1),
            portrait_path=portrait_path,
            weapon_stack_key=stack_key,
            weapon_name=weapon_name,
            weapon_image_path=weapon_image_path,
            weapon_tooltip=_postdraft_weapon_tooltip(session, seat, stack_key),
            selected_assignment=bool(
                _selected_assignment_character(self.workspace._draft_view_state())
                == (seat, character_id)
            ),
            selected_weapon_character=bool(
                _selected_weapon_character(self.workspace._draft_view_state())
                == (seat, character_id)
            ),
            clear_mode=(
                "assignment"
                if stage == PVP_DRAFT_STAGE_ASSIGNMENT
                else "weapon"
                if stage == PVP_DRAFT_STAGE_WEAPONS and character_id and stack_key
                else ""
            ),
            clickable=bool(
                stage == PVP_DRAFT_STAGE_ASSIGNMENT
                or (stage == PVP_DRAFT_STAGE_WEAPONS and character_id)
            ),
        )
        slot.clicked.connect(
            lambda s=seat, t=team_index, i=slot_index: (
                self._on_target_slot_clicked(stage, s, t, i)
            )
        )
        slot.clear_assignment_requested.connect(
            lambda s=seat, t=team_index, i=slot_index: (
                self.workspace.clear_assignment_slot(s, t, i)
            )
        )
        if character_id:
            slot.clear_weapon_requested.connect(
                lambda s=seat, c=character_id: self.workspace.clear_weapon_assignment(s, c)
            )
        self.team_slot_buttons_by_key[(seat, team_index, slot_index)] = slot
        return slot

    def _on_target_slot_clicked(
        self,
        stage: str,
        seat: str,
        team_index: int,
        slot_index: int,
    ) -> None:
        if stage == PVP_DRAFT_STAGE_ASSIGNMENT:
            self.workspace.assign_selected_character_to_slot(seat, team_index, slot_index)
            return
        character_id = self.workspace.assignment_slots_by_seat[seat][team_index][slot_index]
        if character_id and stage == PVP_DRAFT_STAGE_WEAPONS:
            self.workspace.select_weapon_character(seat, character_id)

    def _add_timer_result_area(
        self,
        layout: QVBoxLayout,
        session: PvpActiveDraftSession,
        stage: str,
        seat: str,
    ) -> None:
        timer_frame = QFrame()
        timer_frame.setObjectName("pvp-timer-area")
        timer_layout = QVBoxLayout(timer_frame)
        timer_layout.setContentsMargins(5, 5, 5, 5)
        timer_layout.setSpacing(3)
        show_inputs = stage == PVP_DRAFT_STAGE_TIMERS_RESULTS
        show_result = stage == PVP_DRAFT_STAGE_COMPLETED_RESULT
        if show_inputs or show_result:
            for index, chamber_id in enumerate(PVP_TIMER_CHAMBERS):
                row = QFrame()
                row.setObjectName("pvp-timer-row")
                row_layout = QHBoxLayout(row)
                row_layout.setContentsMargins(0, 0, 0, 0)
                row_layout.setSpacing(4)
                label = QLabel(f"T{chamber_id}")
                label.setObjectName("pvp_deck_info_line")
                row_layout.addWidget(label)
                if show_inputs:
                    line = QLineEdit()
                    line.setPlaceholderText("mm:ss")
                    line.setText(self.workspace.timer_texts_by_seat[seat][index])
                    line.textChanged.connect(
                        lambda text, s=seat, i=index: self._on_timer_text_changed(s, i, text)
                    )
                    self.timer_inputs_by_key[(seat, index)] = line
                    row_layout.addWidget(line, 1)
                else:
                    value = QLabel(_completed_timer_text(session, seat, index))
                    value.setObjectName("pvp_deck_info_line")
                    row_layout.addWidget(value, 1)
                timer_layout.addWidget(row)
        else:
            dps = QLabel(tr("app_shell.pvp.post.dps_unavailable"))
            dps.setObjectName("small_muted")
            timer_layout.addWidget(dps)
        total = QLabel(
            tr("app_shell.pvp.post.timer_total").format(
                total=_format_seconds(_postdraft_timer_total(session, self.workspace._draft_view_state(), seat)),
            )
        )
        total.setObjectName("small_muted")
        self.timer_total_labels_by_seat[seat] = total
        timer_layout.addWidget(total)
        if show_result:
            result = QLabel(_result_line_for_seat(session, seat))
            result.setObjectName("pvp_deck_info_line")
            result.setWordWrap(True)
            timer_layout.addWidget(result)
        layout.addWidget(timer_frame)

    def _on_timer_text_changed(self, seat: str, index: int, text: str) -> None:
        self.workspace.set_timer_text(seat, index, text)
        total_label = self.timer_total_labels_by_seat.get(seat)
        if total_label is None:
            return
        total = 0
        for timer_index in range(len(PVP_TIMER_CHAMBERS)):
            line = self.timer_inputs_by_key.get((seat, timer_index))
            seconds = _parse_timer_text(line.text() if line is not None else "")
            if seconds is not None:
                total += seconds
        total_label.setText(
            tr("app_shell.pvp.post.timer_total").format(
                total=_format_seconds(total),
            )
        )


__all__ = ["PvpDraftRightPanel"]
