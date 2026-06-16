from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

from localization import tr
from run_workspace.right_panel_prototype_view_model import (
    RightPanelSlotPrototypeViewModel,
    RightPanelTeamPrototypeViewModel,
)
from run_workspace.team_card_view_model import EMPTY_SLOT_TITLE
from ui.right_panel.common.slot_card import RightPanelSlotCardWidget
from ui.right_panel.common.slot_parts import slot_portrait_fallback
from ui.right_panel.common.team_card import RightPanelTeamCardWidget
from ui.right_panel.pvp._shared import (
    PVP_DECKS_RIGHT_PANEL_STYLE,
    PVP_DRAFT_STAGE_ASSIGNMENT,
    PVP_DRAFT_STAGE_COMPLETED_RESULT,
    PVP_DRAFT_STAGE_DRAFT,
    PVP_DRAFT_STAGE_TIMERS_RESULTS,
    PVP_DRAFT_STAGE_WEAPONS,
    PVP_PAGE_PLAY,
    PVP_SEATS,
    PVP_TIMER_CHAMBERS,
    _asset_image_path,
    _assignment_slots,
    _clear_layout,
    _completed_timer_text,
    _draft_action_detail,
    _draft_action_log_lines,
    _draft_action_title,
    _draft_is_complete,
    _draft_panel_status_lines,
    _draft_result_zone_title,
    _entry_display_name_for_id,
    _format_seconds,
    _is_post_draft_stage,
    _mapping,
    _parse_timer_text,
    _postdraft_target_object_name,
    _postdraft_timer_total,
    _postdraft_weapon_tooltip,
    _result_line_for_seat,
    _seat_label,
    _selected_assignment_character,
    _selected_weapon_character,
    _weapon_assignment_map,
    _weapon_display_name,
)
from ui.right_panel.pvp.draft.pick_ban.result_zone import PvpDraftResultZoneWidget
from ui.utils.overlay_scroll import OverlayVerticalScrollArea


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

        self.action_frame = QFrame()
        self.action_frame.setObjectName("pvp_draft_action_card")
        action_layout = QVBoxLayout(self.action_frame)
        action_layout.setContentsMargins(9, 8, 9, 8)
        action_layout.setSpacing(4)
        self.action_label = QLabel()
        self.action_label.setObjectName("pvp_draft_action_title")
        self.action_label.setWordWrap(True)
        action_layout.addWidget(self.action_label)
        self.action_detail_label = QLabel()
        self.action_detail_label.setObjectName("small_muted")
        self.action_detail_label.setWordWrap(True)
        action_layout.addWidget(self.action_detail_label)
        root.addWidget(self.action_frame)

        self.match_frame = QFrame()
        self.match_frame.setObjectName("pvp_postdraft_match_panel")
        self.match_layout = QVBoxLayout(self.match_frame)
        self.match_layout.setContentsMargins(0, 0, 0, 0)
        self.match_layout.setSpacing(6)
        self.match_scroll = OverlayVerticalScrollArea()
        self.match_scroll.setObjectName("pvp_postdraft_match_scroll")
        self.match_scroll.setWidgetResizable(True)
        self.match_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.match_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.match_scroll.setWidget(self.match_frame)
        root.addWidget(self.match_scroll, 1)
        self.target_zone_frames_by_seat: dict[str, QFrame] = {}
        self.team_slot_buttons_by_key: dict[tuple[str, int, int], RightPanelSlotCardWidget] = {}
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

        self.result_zone_frames: dict[tuple[str, str], PvpDraftResultZoneWidget] = {}
        self.result_zone_widgets = self.result_zone_frames
        for seat in ("player_1", "player_2"):
            for zone in ("picked", "banned"):
                frame = PvpDraftResultZoneWidget(
                    seat=seat,
                    zone=zone,
                    title=_draft_result_zone_title(seat, zone),
                )
                root.addWidget(frame)
                key = (seat, zone)
                self.result_zone_frames[key] = frame

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
        self.action_frame.setVisible(False)
        self.match_scroll.setVisible(False)
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
        self.action_frame.setVisible(not post_draft_stage)
        if not post_draft_stage:
            self.action_label.setText(_draft_action_title(board))
            self.action_detail_label.setText(_draft_action_detail(board))
        if post_draft_stage:
            self._rebuild_match_panel(board, stage)
        else:
            _clear_layout(self.match_layout)
            self._clear_match_registries()
        self.match_scroll.setVisible(post_draft_stage)
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
            frame.set_title(_draft_result_zone_title(seat, zone))
            frame.set_items(self._result_zone_items(board, seat=seat, zone=zone))
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

    def _result_zone_items(
        self,
        board: Mapping[str, Any],
        *,
        seat: str,
        zone: str,
    ) -> list[dict[str, Any]]:
        result_zones = _mapping(_mapping(board.get("unified_pool")).get("result_zones"))
        seat_zones = _mapping(result_zones.get(seat))
        character_ids = seat_zones.get(zone)
        if not isinstance(character_ids, list):
            return []
        items: list[dict[str, Any]] = []
        for character_id_value in character_ids:
            character_id = str(character_id_value or "").strip()
            if not character_id:
                continue
            items.append(
                {
                    "character_id": character_id,
                    "name": _entry_display_name_for_id(board, character_id),
                    "portrait_path": _asset_image_path(
                        self.workspace.draft_workspace._character_assets_by_id.get(
                            character_id,
                        )
                    ),
                }
            )
        return items

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

            for team_index in range(2):
                team_widget = RightPanelTeamCardWidget(
                    self._build_target_team_model(
                        board,
                        session,
                        stage,
                        seat,
                        team_index,
                    )
                )
                team_widget.setProperty("seat", seat)
                team_widget.setProperty("teamIndex", team_index)
                team_widget.slot_selected.connect(
                    lambda model_team_index, model_slot_index, s=seat: (
                        self._on_target_slot_clicked(
                            stage,
                            s,
                            model_team_index,
                            model_slot_index,
                        )
                    )
                )
                self._register_target_team_slots(
                    team_widget,
                    board,
                    session,
                    seat,
                    team_index,
                )
                zone_layout.addWidget(team_widget)

            self._add_timer_result_area(zone_layout, session, stage, seat)
            self.match_layout.addWidget(zone, 1)

    def _build_target_team_model(
        self,
        board: Mapping[str, Any],
        session: PvpActiveDraftSession,
        stage: str,
        seat: str,
        team_index: int,
    ) -> RightPanelTeamPrototypeViewModel:
        slots = _assignment_slots(self.workspace._draft_view_state(), seat)
        return RightPanelTeamPrototypeViewModel(
            team_index=team_index,
            slots=tuple(
                self._build_target_slot_model(
                    board,
                    session,
                    stage,
                    seat,
                    team_index,
                    slot_index,
                    slots[team_index][slot_index],
                )
                for slot_index in range(4)
            ),
        )

    def _build_target_slot_model(
        self,
        board: Mapping[str, Any],
        session: PvpActiveDraftSession,
        stage: str,
        seat: str,
        team_index: int,
        slot_index: int,
        character_id: str | None,
    ) -> RightPanelSlotPrototypeViewModel:
        if not character_id:
            return RightPanelSlotPrototypeViewModel(
                team_index=team_index,
                slot_index=slot_index,
                is_empty=True,
                is_selected=False,
                character_title=EMPTY_SLOT_TITLE,
                character_meta="",
                portrait_label="+",
                portrait_path="",
                weapon_label="",
                weapon_square_label="WPN",
                weapon_image_path="",
                weapon_tooltip="",
                build_label="",
                artifact_square_label="ART",
                artifact_image_path="",
                build_mini_sets=(),
                stat_badge="EMPTY",
                warning_count=0,
                warning_tooltip="",
            )

        character_name = _entry_display_name_for_id(board, character_id) or character_id
        portrait_path = _asset_image_path(
            self.workspace.draft_workspace._character_assets_by_id.get(
                character_id,
            )
        )
        stack_key = _weapon_assignment_map(self.workspace._draft_view_state(), seat).get(
            character_id,
            "",
        )
        weapon_name = _weapon_display_name(session, seat, stack_key)
        weapon_image_path = _asset_image_path(
            self.workspace.draft_workspace._weapon_assets_by_stack_key.get(stack_key)
        )
        selected = bool(
            _selected_assignment_character(self.workspace._draft_view_state())
            == (seat, character_id)
            or _selected_weapon_character(self.workspace._draft_view_state())
            == (seat, character_id)
        )
        return RightPanelSlotPrototypeViewModel(
            team_index=team_index,
            slot_index=slot_index,
            is_empty=False,
            is_selected=selected,
            character_title=character_name,
            character_meta=self._target_character_meta(session, seat, character_id),
            portrait_label=slot_portrait_fallback(character_name, slot_index),
            portrait_path=portrait_path,
            weapon_label=weapon_name,
            weapon_square_label=self._square_label(weapon_name, fallback="WPN"),
            weapon_image_path=weapon_image_path,
            weapon_tooltip=_postdraft_weapon_tooltip(session, seat, stack_key),
            build_label="",
            artifact_square_label="ART",
            artifact_image_path="",
            build_mini_sets=(),
            stat_badge=self._target_stat_badge(session, seat, character_id),
            warning_count=0,
            warning_tooltip="",
        )

    def _register_target_team_slots(
        self,
        team_widget: RightPanelTeamCardWidget,
        board: Mapping[str, Any],
        session: PvpActiveDraftSession,
        seat: str,
        team_index: int,
    ) -> None:
        slots = _assignment_slots(self.workspace._draft_view_state(), seat)
        weapon_map = _weapon_assignment_map(self.workspace._draft_view_state(), seat)
        for slot_index, slot_widget in enumerate(team_widget.slot_widgets()):
            character_id = slots[team_index][slot_index] or ""
            stack_key = weapon_map.get(character_id, "")
            slot_widget.setProperty("pvpTargetSlot", True)
            slot_widget.setProperty("seat", seat)
            slot_widget.setProperty("teamIndex", team_index)
            slot_widget.setProperty("slotIndex", slot_index)
            slot_widget.setProperty("characterId", character_id)
            slot_widget.setProperty("stackKey", stack_key)
            slot_widget.setProperty("hasCharacter", bool(character_id))
            slot_widget.setProperty(
                "clickable",
                bool(
                    self.workspace.draft_stage == PVP_DRAFT_STAGE_ASSIGNMENT
                    or (
                        self.workspace.draft_stage == PVP_DRAFT_STAGE_WEAPONS
                        and character_id
                    )
                ),
            )
            portrait = (
                slot_widget.findChild(QLabel, "PortraitBox")
                or slot_widget.findChild(QLabel, "PortraitBoxEmpty")
            )
            weapon = (
                slot_widget.findChild(QLabel, "MiniEquipBox")
                or slot_widget.findChild(QLabel, "MiniEquipBoxMissing")
            )
            slot_widget.setProperty(
                "hasPortraitPixmap",
                bool(portrait is not None and portrait.property("hasPixmap")),
            )
            slot_widget.setProperty(
                "hasWeaponPixmap",
                bool(weapon is not None and weapon.property("hasPixmap")),
            )
            self.team_slot_buttons_by_key[(seat, team_index, slot_index)] = slot_widget

    def _target_character_meta(
        self,
        session: PvpActiveDraftSession,
        seat: str,
        character_id: str,
    ) -> str:
        try:
            character = session.controller.session_state.deck_for(seat).character_by_id.get(
                character_id
            )
        except Exception:
            character = None
        if character is None:
            return ""
        parts: list[str] = []
        if character.level is not None:
            parts.append(f"Lv.{character.level}")
        if character.constellation is not None:
            parts.append(f"C{character.constellation}")
        if character.element:
            parts.append(str(character.element))
        if character.weapon_type:
            parts.append(str(character.weapon_type))
        return " | ".join(parts)

    def _target_stat_badge(
        self,
        session: PvpActiveDraftSession,
        seat: str,
        character_id: str,
    ) -> str:
        try:
            character = session.controller.session_state.deck_for(seat).character_by_id.get(
                character_id
            )
        except Exception:
            character = None
        if character is None or character.constellation is None:
            return ""
        return f"C{character.constellation}"

    def _square_label(self, text: str, *, fallback: str) -> str:
        words = [word for word in str(text or "").replace("#", " ").split() if word]
        if not words:
            return fallback
        if words[0].isdigit():
            return f"#{words[0]}"
        if len(words) == 1:
            return words[0][:3].upper()
        return "".join(word[0] for word in words[:3]).upper()

    def _on_target_slot_clicked(
        self,
        stage: str,
        seat: str,
        team_index: int,
        slot_index: int,
    ) -> None:
        if stage == PVP_DRAFT_STAGE_ASSIGNMENT:
            current = self.workspace.assignment_slots_by_seat[seat][team_index][slot_index]
            if (
                current
                and _selected_assignment_character(self.workspace._draft_view_state())
                == (seat, current)
            ):
                self.workspace.clear_assignment_slot(seat, team_index, slot_index)
                return
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
