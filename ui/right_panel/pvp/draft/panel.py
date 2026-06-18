from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QVBoxLayout, QWidget

from localization import tr
from run_workspace.right_panel_prototype_view_model import RightPanelPrototypeViewModel
from ui.right_panel.common.slot_card import RightPanelSlotCardWidget
from ui.right_panel.live_run.panel import RunRightPanelWidget
from ui.right_panel.pvp._shared import (
    PVP_DECKS_RIGHT_PANEL_STYLE,
    PVP_DRAFT_STAGE_ASSIGNMENT,
    PVP_DRAFT_STAGE_COMPLETED_RESULT,
    PVP_DRAFT_STAGE_DRAFT,
    PVP_DRAFT_STAGE_WEAPONS,
    PVP_PAGE_PLAY,
    PVP_SEATS,
    _asset_image_path,
    _clear_layout,
    _draft_action_detail,
    _draft_action_log_lines,
    _draft_action_title,
    _draft_is_complete,
    _draft_panel_status_lines,
    _draft_result_zone_title,
    _entry_display_name_for_id,
    _is_post_draft_stage,
    _mapping,
    _postdraft_target_object_name,
    _seat_label,
)
from ui.right_panel.pvp.draft.pick_ban.result_zone import PvpDraftResultZoneWidget
from ui.utils.overlay_scroll import OverlayVerticalScrollArea


class PvpPostDraftRunPanel(RunRightPanelWidget):
    """PvP-owned state rendered through the production live-run right panel."""

    def __init__(
        self,
        model: RightPanelPrototypeViewModel,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(
            model,
            parent,
            show_mode_tabs=False,
            show_chamber_table=False,
            show_run_actions=False,
        )
        self.setObjectName("pvp_postdraft_run_panel")

    def slot_widgets(self) -> list[RightPanelSlotCardWidget]:
        return list(self._slot_widgets)


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
        self.postdraft_run_panels_by_seat: dict[str, PvpPostDraftRunPanel] = {}
        self.collapsed_postdraft_seats: set[str] = {"player_2"}

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
        self.status_frame.setVisible(has_session and not post_draft_stage)
        self.clear_button.setVisible(has_session and not post_draft_stage)
        self.play_button.setVisible(not post_draft_stage)
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
        status_lines = (
            _draft_panel_status_lines(board, stage=stage, workspace=self.workspace)
            if not post_draft_stage
            else []
        )
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

    def _clear_match_registries(self) -> None:
        self.target_zone_frames_by_seat.clear()
        self.team_slot_buttons_by_key.clear()
        self.postdraft_run_panels_by_seat.clear()

    def _rebuild_match_panel(self, board: Mapping[str, Any], stage: str) -> None:
        _clear_layout(self.match_layout)
        self._clear_match_registries()
        session = self.workspace.active_draft_session
        build_context = self.workspace.build_flow_context
        if session is None or build_context is None:
            return
        for seat in PVP_SEATS:
            seat_context = build_context.seat(seat)
            if seat_context is None:
                continue
            zone = QFrame()
            zone.setObjectName(_postdraft_target_object_name(seat))
            zone.setProperty("seat", seat)
            zone_layout = QVBoxLayout(zone)
            zone_layout.setContentsMargins(7, 7, 7, 7)
            zone_layout.setSpacing(5)
            self.target_zone_frames_by_seat[seat] = zone

            collapsed = self.workspace.is_build_seat_collapsed(seat)
            toggle_prefix = ">" if collapsed else "v"
            ready_marker = " ready" if seat_context.ready else ""
            toggle = QPushButton(f"{toggle_prefix} {_seat_label(seat)}{ready_marker}")
            toggle.setObjectName("pvp_postdraft_player_toggle")
            toggle.clicked.connect(
                lambda _checked=False, s=seat: self._toggle_postdraft_seat(s)
            )
            zone_layout.addWidget(toggle)

            panel = PvpPostDraftRunPanel(
                seat_context.right_panel_model()
            )
            panel.setProperty("seat", seat)
            panel.slot_selected.connect(
                lambda team_index, slot_index, s=seat: (
                    self.workspace.handle_build_slot_clicked(s, team_index, slot_index)
                )
            )
            panel.setVisible(not collapsed)
            self.postdraft_run_panels_by_seat[seat] = panel
            self._register_target_run_panel_slots(panel, seat, seat_context)
            zone_layout.addWidget(panel)

            ready_button = QPushButton(tr("app_shell.pvp.post.ready_button"))
            ready_button.setObjectName("pvp_primary_button")
            ready_button.setEnabled(
                not seat_context.ready and seat_context.ready_candidate()
            )
            ready_button.clicked.connect(
                lambda _checked=False, s=seat: self.workspace.ready_build_seat(s)
            )
            ready_button.setVisible(
                not collapsed and stage in {PVP_DRAFT_STAGE_ASSIGNMENT, PVP_DRAFT_STAGE_WEAPONS}
            )
            zone_layout.addWidget(ready_button)
            self.match_layout.addWidget(zone, 0 if collapsed else 1)

    def _toggle_postdraft_seat(self, seat: str) -> None:
        self.workspace.toggle_build_seat_collapsed(seat)

    def _register_target_run_panel_slots(
        self,
        panel: PvpPostDraftRunPanel,
        seat: str,
        seat_context: Any,
    ) -> None:
        for slot_widget in panel.slot_widgets():
            team_index, slot_index = slot_widget.slot_position()
            character_id = ""
            stack_key = ""
            try:
                slot = seat_context.controller.state.team(team_index).slot(slot_index)
                if slot.character is not None:
                    character_id = str(slot.character.id or "").strip()
                if slot.weapon is not None:
                    stack_key = str(slot.weapon.variant_key or "").strip()
            except Exception:
                pass
            slot_widget.setProperty("pvpTargetSlot", True)
            slot_widget.setProperty("seat", seat)
            slot_widget.setProperty("teamIndex", team_index)
            slot_widget.setProperty("slotIndex", slot_index)
            slot_widget.setProperty("characterId", character_id)
            slot_widget.setProperty("stackKey", stack_key)
            slot_widget.setProperty("hasCharacter", bool(character_id))
            slot_widget.setProperty("clickable", True)
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

__all__ = ["PvpDraftRightPanel", "PvpPostDraftRunPanel"]
