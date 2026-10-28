from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

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
    PVP_POSTDRAFT_HEADER_HEIGHT,
    PVP_POSTDRAFT_SECTION_SPACING,
    PVP_SEATS,
    _asset_image_path,
    build_pvp_draft_grid_item,
    _clear_layout,
    _draft_action_detail,
    _draft_action_log_lines,
    _draft_action_title,
    _draft_is_complete,
    _draft_result_zone_title,
    _is_post_draft_stage,
    _mapping,
    _configure_postdraft_seat_toggle,
    _postdraft_seat_toggle_text,
    _postdraft_target_object_name,
    _refresh_postdraft_seat_toggle_style,
)
from ui.right_panel.pvp.draft.pick_ban.result_zone import PvpDraftResultZoneWidget
from ui.utils.overlay_scroll import OverlayVerticalScrollArea


class PvpPostDraftSeatFrame(QFrame):
    """Right-dock accordion section; player color lives in its header."""

    def __init__(self, seat: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.seat = seat
        self.setObjectName(_postdraft_target_object_name(seat))
        self.setProperty("seat", seat)


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
        self.setMinimumWidth(0)

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
        self.match_layout.setSpacing(PVP_POSTDRAFT_SECTION_SPACING)
        self.match_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
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
        self.postdraft_toggle_buttons_by_seat: dict[str, QPushButton] = {}
        self.postdraft_ready_buttons_by_seat: dict[str, QPushButton] = {}
        self._last_match_stage = ""
        self._pending_match_stage = ""
        self._pending_match_seats: set[str] = set()
        self._last_collapsed_by_seat: dict[str, bool] = {}
        self._match_update_timer = QTimer(self)
        self._match_update_timer.setSingleShot(True)
        self._match_update_timer.timeout.connect(self._flush_deferred_match_panel_update)
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
        self.result_zone_rows_by_seat: dict[str, QWidget] = {}
        for seat in ("player_1", "player_2"):
            seat_row = QWidget()
            seat_row.setObjectName("pvp_draft_result_player_row")
            self.result_zone_rows_by_seat[seat] = seat_row
            seat_layout = QHBoxLayout(seat_row)
            seat_layout.setContentsMargins(0, 0, 0, 0)
            seat_layout.setSpacing(6)
            for zone in ("picked", "banned"):
                frame = PvpDraftResultZoneWidget(
                    seat=seat,
                    zone=zone,
                    title=_draft_result_zone_title(seat, zone),
                )
                seat_layout.addWidget(frame, 3 if zone == "picked" else 1)
                key = (seat, zone)
                self.result_zone_frames[key] = frame
            root.addWidget(seat_row, 1)

        self._log_expanded = False
        self.log_toggle_button = QPushButton()
        self.log_toggle_button.setObjectName("pvp_draft_log_toggle")
        self.log_toggle_button.clicked.connect(self._toggle_log)
        root.addWidget(self.log_toggle_button)

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
        self.retranslate_ui()
        self.refresh()

    def refresh(self) -> None:
        session = self.workspace.active_draft_session
        has_session = session is not None
        self.title_label.setVisible(not has_session)
        self.empty_label.setVisible(not has_session)
        self.action_frame.setVisible(False)
        self.match_scroll.setVisible(False)
        self.status_frame.setVisible(False)
        self.log_toggle_button.setVisible(has_session)
        self.clear_button.setVisible(has_session)
        self.clear_button.setEnabled(has_session)
        self.stage_button.setVisible(has_session)
        self.play_button.setVisible(True)
        self.message_label.setText(self.workspace.last_draft_status())
        self.message_label.setVisible(bool(self.message_label.text()))

        if session is None:
            self._reset_postdraft_pane_geometry()
            _clear_layout(self.match_layout)
            self._clear_match_registries()
            for label in (*self.status_labels, *self.log_labels):
                label.clear()
                label.setVisible(False)
            for frame in self.result_zone_frames.values():
                frame.setVisible(False)
            for row in self.result_zone_rows_by_seat.values():
                row.setVisible(False)
            self.stage_button.setVisible(False)
            return

        stage = self.workspace.draft_stage
        post_draft_stage = _is_post_draft_stage(stage)
        self.status_frame.setVisible(False)
        self.clear_button.setVisible(has_session and not post_draft_stage)
        self.play_button.setVisible(not post_draft_stage)
        self.action_frame.setVisible(False)
        if post_draft_stage:
            self._refresh_postdraft_match_panel(stage)
            self.match_scroll.setVisible(True)
            if stage in {PVP_DRAFT_STAGE_ASSIGNMENT, PVP_DRAFT_STAGE_WEAPONS}:
                self._schedule_postdraft_pane_geometry_sync()
            else:
                self._reset_postdraft_pane_geometry()
            self.stage_button.setVisible(False)
            for label in (*self.status_labels, *self.log_labels):
                label.clear()
                label.setVisible(False)
            for frame in self.result_zone_frames.values():
                frame.setVisible(False)
            for row in self.result_zone_rows_by_seat.values():
                row.setVisible(False)
            self.log_toggle_button.setVisible(False)
            return

        self._reset_postdraft_pane_geometry()
        board = session.board_dict()
        if not post_draft_stage:
            self.action_label.setText("")
            self.action_detail_label.setText("")
        _clear_layout(self.match_layout)
        self._clear_match_registries()
        self.match_scroll.setVisible(post_draft_stage)
        for label in self.status_labels:
            label.clear()
            label.setVisible(False)

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
        for row in self.result_zone_rows_by_seat.values():
            row.setVisible(show_draft_summary)

        log_lines = _draft_action_log_lines(board, limit=len(self.log_labels))
        self.log_toggle_button.setVisible(show_draft_summary)
        self._refresh_log_toggle_text()
        for index, label in enumerate(self.log_labels):
            text = log_lines[index] if index < len(log_lines) else ""
            label.setText(text)
            label.setVisible(show_draft_summary and self._log_expanded and bool(text))

    def showEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().showEvent(event)
        self._schedule_postdraft_pane_geometry_sync()

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().resizeEvent(event)
        self._schedule_postdraft_pane_geometry_sync()

    def _schedule_postdraft_pane_geometry_sync(self) -> None:
        if self.workspace.draft_stage not in {
            PVP_DRAFT_STAGE_ASSIGNMENT,
            PVP_DRAFT_STAGE_WEAPONS,
        }:
            return
        QTimer.singleShot(0, self._sync_postdraft_pane_geometry)

    def _reset_postdraft_pane_geometry(self) -> None:
        self.match_layout.setContentsMargins(0, 0, 0, 0)
        self.match_frame.setMinimumHeight(0)
        self.match_frame.setMaximumHeight(16777215)
        self.match_frame.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        self.workspace.draft_workspace.set_postdraft_alignment_margins(0, 0)
        self.workspace.draft_workspace.lock_postdraft_content_height(None)

    def _sync_postdraft_pane_geometry(self) -> None:
        if self.workspace.draft_stage not in {
            PVP_DRAFT_STAGE_ASSIGNMENT,
            PVP_DRAFT_STAGE_WEAPONS,
        }:
            self._reset_postdraft_pane_geometry()
            return
        left_viewport = self.workspace.draft_workspace.scroll_area.viewport()
        right_viewport = self.match_scroll.viewport()
        if (
            not left_viewport.isVisible()
            or not right_viewport.isVisible()
            or left_viewport.width() <= 0
            or left_viewport.height() <= 0
            or right_viewport.width() <= 0
            or right_viewport.height() <= 0
        ):
            return

        left_top = left_viewport.mapToGlobal(QPoint(0, 0)).y()
        right_top = right_viewport.mapToGlobal(QPoint(0, 0)).y()
        left_bottom = left_top + left_viewport.height()
        right_bottom = right_top + right_viewport.height()
        shared_top = max(left_top, right_top)
        shared_bottom = min(left_bottom, right_bottom)
        if shared_bottom <= shared_top:
            return

        # These outer scroll areas are stage hosts, not seat-body scrollers.
        # Lock their content to the viewport so focused controls or stale size
        # hints cannot grow/scroll one pane independently. Weapon and run-card
        # bodies retain their own overlay scroll areas inside each fixed zone.
        self.workspace.draft_workspace.lock_postdraft_content_height(
            left_viewport.height()
        )
        self.match_frame.setFixedHeight(right_viewport.height())
        self.match_frame.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self.match_scroll.verticalScrollBar().setValue(0)

        left_top_margin = shared_top - left_top
        left_bottom_margin = left_bottom - shared_bottom
        right_top_margin = shared_top - right_top
        right_bottom_margin = right_bottom - shared_bottom
        self.workspace.draft_workspace.set_postdraft_alignment_margins(
            left_top_margin,
            left_bottom_margin,
        )
        desired_right = (
            0,
            right_top_margin,
            0,
            right_bottom_margin,
        )
        margins = self.match_layout.contentsMargins()
        current_right = (
            margins.left(),
            margins.top(),
            margins.right(),
            margins.bottom(),
        )
        if current_right != desired_right:
            self.match_layout.setContentsMargins(*desired_right)
        self._apply_synchronized_postdraft_zone_heights(
            shared_bottom - shared_top
        )
        self.match_layout.invalidate()
        self.match_layout.activate()

    def _apply_synchronized_postdraft_zone_heights(self, shared_height: int) -> None:
        available = max(
            0,
            int(shared_height) - PVP_POSTDRAFT_SECTION_SPACING,
        )
        collapsed = {
            seat: self.workspace.is_build_seat_collapsed(seat)
            for seat in PVP_SEATS
        }
        if all(collapsed.values()):
            heights = {
                seat: PVP_POSTDRAFT_HEADER_HEIGHT
                for seat in PVP_SEATS
            }
        elif collapsed["player_1"]:
            heights = {
                "player_1": PVP_POSTDRAFT_HEADER_HEIGHT,
                "player_2": max(
                    PVP_POSTDRAFT_HEADER_HEIGHT,
                    available - PVP_POSTDRAFT_HEADER_HEIGHT,
                ),
            }
        elif collapsed["player_2"]:
            heights = {
                "player_1": max(
                    PVP_POSTDRAFT_HEADER_HEIGHT,
                    available - PVP_POSTDRAFT_HEADER_HEIGHT,
                ),
                "player_2": PVP_POSTDRAFT_HEADER_HEIGHT,
            }
        else:
            player_1_height = available // 2
            heights = {
                "player_1": player_1_height,
                "player_2": available - player_1_height,
            }

        left_zones = self.workspace.draft_workspace.source_zone_frames_by_seat
        for seat, height in heights.items():
            height = max(PVP_POSTDRAFT_HEADER_HEIGHT, int(height))
            for zone in (
                left_zones.get(seat),
                self.target_zone_frames_by_seat.get(seat),
            ):
                if zone is None:
                    continue
                zone.setMinimumHeight(height)
                zone.setMaximumHeight(height)
                zone.setSizePolicy(
                    QSizePolicy.Policy.Expanding,
                    QSizePolicy.Policy.Fixed,
                )
        left_frame = self.workspace.draft_workspace._scoped_build_source_frame
        left_layout = left_frame.layout() if left_frame is not None else None
        if left_layout is not None:
            left_layout.invalidate()
            left_layout.activate()

    def retranslate_ui(self) -> None:
        self.title_label.setText(tr("app_shell.pvp.draft.title"))
        self.empty_label.setText(tr("app_shell.pvp.draft.no_active_body"))
        self._refresh_log_toggle_text()
        self.clear_button.setText(tr("app_shell.pvp.draft.abandon"))
        self.play_button.setText(tr("app_shell.pvp.draft.back_to_play"))
        self.refresh()

    def refresh_player_colors(self) -> None:
        for seat, button in self.postdraft_toggle_buttons_by_seat.items():
            _refresh_postdraft_seat_toggle_style(button, seat=seat)
        for frame in self.result_zone_frames.values():
            frame.refresh_player_color()
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
    ) -> list[Any]:
        result_zones = _mapping(_mapping(board.get("unified_pool")).get("result_zones"))
        seat_zones = _mapping(result_zones.get(seat))
        character_ids = seat_zones.get(zone)
        if not isinstance(character_ids, list):
            return []
        entries = _mapping(board.get("unified_pool")).get("entries")
        entries_by_id = (
            {
                str(_mapping(entry).get("character_id") or ""): _mapping(entry)
                for entry in entries
            }
            if isinstance(entries, list)
            else {}
        )
        items: list[Any] = []
        for character_id_value in character_ids:
            character_id = str(character_id_value or "").strip()
            if not character_id:
                continue
            items.append(
                build_pvp_draft_grid_item(
                    entries_by_id.get(character_id, {"character_id": character_id}),
                    portrait_path=_asset_image_path(
                        self.workspace.draft_workspace._character_assets_by_id.get(
                            character_id,
                        )
                    ),
                    result_seat=seat,
                    result_zone=zone,
                )
            )
        return items

    def _toggle_log(self) -> None:
        self._log_expanded = not self._log_expanded
        self.refresh()

    def _refresh_log_toggle_text(self) -> None:
        prefix = "v" if self._log_expanded else ">"
        self.log_toggle_button.setText(
            f"{prefix} {tr('app_shell.pvp.draft.action_log_title')}"
        )

    def _on_stage_button_clicked(self) -> None:
        stage = self.workspace.draft_stage
        if stage == PVP_DRAFT_STAGE_DRAFT:
            self.workspace.continue_to_assignment()

    def _clear_match_registries(self) -> None:
        self.target_zone_frames_by_seat.clear()
        self.team_slot_buttons_by_key.clear()
        self.postdraft_run_panels_by_seat.clear()
        self.postdraft_toggle_buttons_by_seat.clear()
        self.postdraft_ready_buttons_by_seat.clear()
        self._last_collapsed_by_seat.clear()
        self._last_match_stage = ""

    def _rebuild_match_panel(self, stage: str) -> None:
        session = self.workspace.active_draft_session
        build_context = self.workspace.build_flow_context
        if session is None or build_context is None:
            _clear_layout(self.match_layout)
            self._clear_match_registries()
            return
        if set(self.postdraft_run_panels_by_seat) == set(PVP_SEATS):
            seats = (
                None
                if self._last_match_stage != stage
                else (build_context.active_seat,)
            )
            self._update_match_panel(stage, seats=seats)
            self._last_match_stage = stage
            return
        _clear_layout(self.match_layout)
        self._clear_match_registries()
        for seat in PVP_SEATS:
            seat_context = build_context.seat(seat)
            if seat_context is None:
                continue
            zone = PvpPostDraftSeatFrame(seat, self.match_frame)
            zone_layout = QVBoxLayout(zone)
            zone_layout.setContentsMargins(0, 0, 0, 0)
            zone_layout.setSpacing(PVP_POSTDRAFT_SECTION_SPACING)
            self.target_zone_frames_by_seat[seat] = zone

            collapsed = self.workspace.is_build_seat_collapsed(seat)
            toggle = _configure_postdraft_seat_toggle(
                QPushButton(zone),
                seat=seat,
            )
            toggle.setChecked(not collapsed)
            toggle.setText(
                _postdraft_seat_toggle_text(
                    seat,
                    collapsed=collapsed,
                    ready=seat_context.ready,
                )
            )
            toggle.clicked.connect(
                lambda _checked=False, s=seat: self._toggle_postdraft_seat(s)
            )
            self.postdraft_toggle_buttons_by_seat[seat] = toggle
            zone_layout.addWidget(toggle)

            panel = PvpPostDraftRunPanel(
                seat_context.right_panel_model(),
                zone,
            )
            panel.setProperty("seat", seat)
            panel.slot_selected.connect(
                lambda team_index, slot_index, s=seat: (
                    self.workspace.handle_build_slot_clicked(s, team_index, slot_index)
                )
            )
            panel.slot_dropped.connect(
                lambda source_team_index,
                source_slot_index,
                target_team_index,
                target_slot_index,
                s=seat: self.workspace.handle_build_slot_dropped(
                    s,
                    source_team_index,
                    source_slot_index,
                    target_team_index,
                    target_slot_index,
                )
            )
            self.postdraft_run_panels_by_seat[seat] = panel
            self._register_target_run_panel_slots(panel, seat, seat_context)
            zone_layout.addWidget(panel, 1)

            ready_button = QPushButton(
                tr("app_shell.pvp.post.ready_button"),
                zone,
            )
            ready_button.setObjectName("pvp_primary_button")
            ready_button.setEnabled(
                not seat_context.ready and seat_context.ready_candidate()
            )
            ready_button.clicked.connect(
                lambda _checked=False, s=seat: self.workspace.ready_build_seat(s)
            )
            self.postdraft_ready_buttons_by_seat[seat] = ready_button
            zone_layout.addWidget(ready_button)
            self.match_layout.addWidget(zone, 0 if collapsed else 1)
            # Visibility is applied only after every widget has a stable
            # parent. Showing panel/Ready while parentless promoted each one
            # to a transient top-level Qt window during this transition.
            panel.setVisible(not collapsed)
            ready_button.setVisible(
                not collapsed
                and stage in {PVP_DRAFT_STAGE_ASSIGNMENT, PVP_DRAFT_STAGE_WEAPONS}
            )
            zone.setVisible(True)
        self._update_match_panel(stage)
        self._last_match_stage = stage

    def _refresh_postdraft_match_panel(self, stage: str) -> None:
        if set(self.postdraft_run_panels_by_seat) != set(PVP_SEATS):
            self._rebuild_match_panel(stage)
            return
        if self._last_match_stage != stage:
            self._update_match_panel(stage)
            self._last_match_stage = stage
            return
        build_context = self.workspace.build_flow_context
        changed_visibility = tuple(
            seat
            for seat in PVP_SEATS
            if self._last_collapsed_by_seat.get(seat)
            != self.workspace.is_build_seat_collapsed(seat)
        )
        if changed_visibility:
            self._match_update_timer.stop()
            self._pending_match_stage = ""
            self._pending_match_seats.clear()
            self._apply_postdraft_visibility(stage, seats=changed_visibility)
            return
        seat = build_context.active_seat if build_context is not None else ""
        self._schedule_match_panel_update(stage, seats=(seat,) if seat else None)

    def _schedule_match_panel_update(
        self,
        stage: str,
        *,
        seats: tuple[str, ...] | None,
    ) -> None:
        self._pending_match_stage = stage
        if seats is None:
            self._pending_match_seats = set(PVP_SEATS)
        else:
            self._pending_match_seats.update(seat for seat in seats if seat)
        self._match_update_timer.start(0)

    def _flush_deferred_match_panel_update(self) -> None:
        stage = self._pending_match_stage or self.workspace.draft_stage
        seats = tuple(self._pending_match_seats) or None
        self._pending_match_stage = ""
        self._pending_match_seats.clear()
        self._update_match_panel(stage, seats=seats)
        self._last_match_stage = stage

    def _update_match_panel(
        self,
        stage: str,
        *,
        seats: tuple[str, ...] | None = None,
    ) -> None:
        build_context = self.workspace.build_flow_context
        if build_context is None:
            return
        target_seats = tuple(seats or PVP_SEATS)
        if seats is None:
            self.team_slot_buttons_by_key.clear()
        else:
            for key in list(self.team_slot_buttons_by_key):
                if key[0] in target_seats:
                    self.team_slot_buttons_by_key.pop(key, None)
        for seat in target_seats:
            seat_context = build_context.seat(seat)
            panel = self.postdraft_run_panels_by_seat.get(seat)
            zone = self.target_zone_frames_by_seat.get(seat)
            if seat_context is None or panel is None or zone is None:
                continue
            panel.set_model(seat_context.right_panel_model())
            self._register_target_run_panel_slots(panel, seat, seat_context)
            ready_button = self.postdraft_ready_buttons_by_seat.get(seat)
            if ready_button is not None:
                ready_button.setEnabled(
                    not seat_context.ready and seat_context.ready_candidate()
                )
            self._apply_postdraft_visibility(stage, seats=(seat,))

    def _apply_postdraft_visibility(
        self,
        stage: str,
        *,
        seats: tuple[str, ...],
    ) -> None:
        for seat in seats:
            seat_context = (
                self.workspace.build_flow_context.seat(seat)
                if self.workspace.build_flow_context is not None
                else None
            )
            panel = self.postdraft_run_panels_by_seat.get(seat)
            zone = self.target_zone_frames_by_seat.get(seat)
            toggle = self.postdraft_toggle_buttons_by_seat.get(seat)
            if seat_context is None or panel is None or zone is None or toggle is None:
                continue
            collapsed = self.workspace.is_build_seat_collapsed(seat)
            toggle.setChecked(not collapsed)
            toggle.setText(
                _postdraft_seat_toggle_text(
                    seat,
                    collapsed=collapsed,
                    ready=seat_context.ready,
                )
            )
            panel.setVisible(not collapsed)
            ready_button = self.postdraft_ready_buttons_by_seat.get(seat)
            if ready_button is not None:
                ready_button.setVisible(
                    not collapsed
                    and stage in {PVP_DRAFT_STAGE_ASSIGNMENT, PVP_DRAFT_STAGE_WEAPONS}
                )
            zone_index = self.match_layout.indexOf(zone)
            if zone_index >= 0:
                self.match_layout.setStretch(zone_index, 0 if collapsed else 1)
            zone.setVisible(True)
            self._sync_postdraft_zone_size(zone, collapsed)
            self._last_collapsed_by_seat[seat] = collapsed
        self.match_layout.invalidate()
        self.match_layout.activate()
        self._sync_postdraft_pane_geometry()
        self._schedule_postdraft_pane_geometry_sync()

    def _toggle_postdraft_seat(self, seat: str) -> None:
        self.workspace.toggle_build_seat_collapsed(seat)

    def _sync_postdraft_zone_size(
        self,
        zone: QFrame,
        collapsed: bool,
    ) -> None:
        if collapsed:
            zone.setMinimumHeight(PVP_POSTDRAFT_HEADER_HEIGHT)
            zone.setMaximumHeight(PVP_POSTDRAFT_HEADER_HEIGHT)
            zone.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Fixed,
            )
            return
        panel = zone.findChild(PvpPostDraftRunPanel, "pvp_postdraft_run_panel")
        if panel is not None:
            # RunRightPanelWidget already owns an overlay scroll area, so it
            # can use the exact half-height assigned by the outer accordion.
            panel.setMinimumHeight(0)
        zone.setMaximumHeight(16777215)
        zone.setMinimumHeight(0)
        zone.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )

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

__all__ = [
    "PvpDraftRightPanel",
    "PvpPostDraftRunPanel",
    "PvpPostDraftSeatFrame",
]
