from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QFrame, QGridLayout, QVBoxLayout, QWidget

from localization import tr
from run_workspace.models import (
    ABYSS_CHAMBER_START_SECONDS,
    ABYSS_TIMER_EDIT_MIN_SECONDS,
)
from run_workspace.pvp.deck_preset import character_id_from_asset, weapon_ref_from_asset
from run_workspace.pvp.weapon_identity import weapon_observed_stack_key
from ui.character_assets import metadata_int
from ui.utils.overlay_scroll import OverlayVerticalScrollArea
from ui.utils.pixel_icon_grid import (
    PixelIconGrid,
    PixelIconGridBadge,
    PixelIconGridFill,
    PixelIconGridItem,
    PixelIconGridOutline,
)
from ui.utils.ui_palette import (
    UI_ACCENT_PVP_BAN,
    UI_ACCENT_PVP_IMMUNE,
    UI_ACCENT_TEAM_1,
    UI_ACCENT_TEAM_2,
    UI_BG_APP,
    UI_BG_BUTTON,
    UI_BG_PANEL,
    UI_BG_PANEL_RAISED,
    UI_BORDER_DEFAULT,
    UI_BORDER_PANEL,
    UI_STATE_DANGER,
    UI_STATE_SUCCESS,
    UI_SELECTION_NEUTRAL_FILL,
    UI_TEXT_MUTED,
    UI_TEXT_PRIMARY,
    UI_TEXT_SECONDARY,
)
from ui.utils.pvp_colors import pvp_player_color

PVP_DECK_ROW_ACTION_SIZE = 24
PVP_DECK_UI_ICON_SIZE = 24
PVP_DECK_UI_ICON_BACKGROUND = UI_BG_PANEL_RAISED
_PVP_DECK_ICON_PIXMAP_CACHE: dict[tuple[object, ...], QPixmap | None] = {}
PVP_PAGE_DECKS = "decks"
PVP_PAGE_PLAY = "play"
PVP_PAGE_DRAFT = "draft"
PVP_DRAFT_STAGE_DRAFT = "draft"
PVP_DRAFT_STAGE_ASSIGNMENT = "assignment"
PVP_DRAFT_STAGE_WEAPONS = "weapons"
PVP_DRAFT_STAGE_TIMERS_RESULTS = "timers_results"
PVP_DRAFT_STAGE_COMPLETED_RESULT = "completed_result"
PVP_DRAFT_STAGE_VALUES = (
    PVP_DRAFT_STAGE_DRAFT,
    PVP_DRAFT_STAGE_ASSIGNMENT,
    PVP_DRAFT_STAGE_WEAPONS,
    PVP_DRAFT_STAGE_TIMERS_RESULTS,
    PVP_DRAFT_STAGE_COMPLETED_RESULT,
)
PVP_SEATS = ("player_1", "player_2")
PVP_TIMER_CHAMBERS = ("1", "2", "3")
PVP_BROWSER_PROJECT_ROOT = Path(__file__).resolve().parents[3]
PVP_DRAFT_BAN_ACCENT = UI_ACCENT_PVP_BAN
PVP_DRAFT_IMMUNE_ACCENT = UI_ACCENT_PVP_IMMUNE

WEAPON_TYPE_FILTER_BY_ID = {
    1: "sword",
    10: "catalyst",
    11: "claymore",
    12: "bow",
    13: "polearm",
}
WEAPON_TYPE_FILTER_ALIASES = {
    "sword": "sword",
    "one_handed_sword": "sword",
    "catalyst": "catalyst",
    "claymore": "claymore",
    "bow": "bow",
    "polearm": "polearm",
}

PVP_DECKS_RIGHT_PANEL_STYLE = f"""
QLineEdit {{
    min-height: 28px;
    padding: 4px 8px;
    border: 1px solid {UI_BORDER_DEFAULT};
    border-radius: 6px;
    background: {UI_BG_APP};
    color: {UI_TEXT_PRIMARY};
}}
QComboBox {{
    min-height: 28px;
    padding: 3px 8px;
    border: 1px solid {UI_BORDER_DEFAULT};
    border-radius: 6px;
    background: {UI_BG_APP};
    color: {UI_TEXT_PRIMARY};
}}
QComboBox:disabled {{
    color: {UI_TEXT_MUTED};
    background: {UI_BG_BUTTON};
}}
QFrame#build_slot_row {{
    border: 1px solid #343b49;
    border-radius: 7px;
    background: {UI_BG_PANEL_RAISED};
}}
QFrame#build_slot_row[selectedDeck="true"] {{
    border-color: #d6b35f;
    background: #3a3224;
}}
QFrame#pvp_deck_expanded_info {{
    border: 1px solid {UI_BORDER_PANEL};
    border-radius: 6px;
    background: {UI_BG_PANEL};
}}
QLabel#small_muted {{
    color: {UI_TEXT_MUTED};
    font-size: 12px;
}}
QLabel#pvp_deck_info_line {{
    color: {UI_TEXT_SECONDARY};
    background: transparent;
    border: none;
    padding: 0px;
    font-size: 12px;
    font-weight: 600;
}}
QFrame#pvp_draft_result_zone {{
    border: 1px solid {UI_BORDER_PANEL};
    border-radius: 6px;
    background: {UI_BG_PANEL};
}}
QFrame#pvp_draft_action_card {{
    border: 1px solid {UI_BORDER_PANEL};
    border-radius: 8px;
    background: {UI_BG_PANEL_RAISED};
}}
QLabel#pvp_draft_action_title {{
    color: {UI_TEXT_PRIMARY};
    font-size: 13px;
    font-weight: 900;
}}
QLabel#pvp_draft_result_title {{
    color: {UI_TEXT_PRIMARY};
    font-size: 12px;
    font-weight: 800;
}}
QWidget#pvp_draft_result_player_row,
QWidget#pvp_draft_result_pick_grid,
QWidget#pvp_draft_result_ban_grid {{
    background: transparent;
    border: none;
}}
QPushButton#pvp_draft_log_toggle {{
    min-height: 24px;
    padding: 2px 6px;
    border: none;
    background: transparent;
    color: {UI_TEXT_SECONDARY};
    font-size: 11px;
    font-weight: 700;
    text-align: left;
}}
QPushButton#pvp_draft_log_toggle:hover {{
    color: {UI_TEXT_PRIMARY};
}}
QPushButton#icon_button,
QPushButton#row_save_button,
QPushButton#row_cancel_button {{
    min-width: {PVP_DECK_ROW_ACTION_SIZE}px;
    max-width: {PVP_DECK_ROW_ACTION_SIZE}px;
    min-height: {PVP_DECK_ROW_ACTION_SIZE}px;
    max-height: {PVP_DECK_ROW_ACTION_SIZE}px;
    padding: 2px;
}}
QPushButton#row_save_button {{
    border-color: {UI_STATE_SUCCESS};
    background: #24452d;
}}
QPushButton#row_save_button:hover {{
    background: #2d5938;
}}
QPushButton#row_cancel_button {{
    border-color: {UI_STATE_DANGER};
    background: #4a2529;
}}
QPushButton#row_cancel_button:hover {{
    background: #5c2d32;
}}
QPushButton#pvp_ruleset_chip {{
    min-height: 24px;
    padding: 2px 7px;
    border: 1px solid {UI_BORDER_DEFAULT};
    border-radius: 6px;
    background: {UI_BG_BUTTON};
    color: {UI_TEXT_SECONDARY};
    font-weight: 700;
}}
QPushButton#pvp_ruleset_chip:disabled {{
    color: #798291;
    background: {UI_BG_BUTTON};
    border-color: #343b49;
}}
QPushButton#pvp_primary_button,
QPushButton#pvp_secondary_button {{
    min-height: 28px;
    padding: 4px 8px;
    border-radius: 6px;
    font-weight: 800;
}}
QPushButton#pvp_primary_button {{
    border: 1px solid {UI_STATE_SUCCESS};
    background: #24452d;
    color: {UI_TEXT_PRIMARY};
}}
QPushButton#pvp_primary_button:hover {{
    background: #2d5938;
}}
QPushButton#pvp_primary_button:disabled {{
    border-color: #343b49;
    background: {UI_BG_BUTTON};
    color: {UI_TEXT_MUTED};
}}
QPushButton#pvp_secondary_button {{
    border: 1px solid {UI_BORDER_DEFAULT};
    background: {UI_BG_BUTTON};
    color: {UI_TEXT_SECONDARY};
}}
QFrame#pvp_postdraft_match_panel {{
    background: transparent;
    border: none;
}}
QFrame#pvp-postdraft-target-player-1,
QFrame#pvp-postdraft-target-player-2 {{
    border: 1px solid {UI_BORDER_PANEL};
    border-radius: 8px;
    background: {UI_BG_PANEL};
}}
QPushButton#pvp_postdraft_player_toggle {{
    min-height: 24px;
    padding: 2px 6px;
    border: none;
    background: transparent;
    color: {UI_TEXT_PRIMARY};
    font-size: 12px;
    font-weight: 900;
    text-align: left;
}}
QPushButton#pvp_postdraft_player_toggle:hover {{
    color: #f1d486;
}}
#TeamSlotRow, #InfoBlock, #DetailsBlock {{
    border: 1px solid #363b43;
    border-radius: 8px;
    background: #202329;
}}
#SlotCard, #SlotCardSelected {{
    border: 2px solid #3f4652;
    border-radius: 7px;
    background: #292e37;
}}
#SlotCardSelected {{
    border-color: #d7b461;
    background: #303743;
}}
#SlotCard[dragHover="true"], #SlotCardSelected[dragHover="true"] {{
    border-color: #7cc7ff;
    background: #334052;
}}
#PortraitBox, #PortraitBoxEmpty {{
    border-radius: 6px;
    border: 1px solid #52606d;
    background: #516679;
    color: #ffffff;
    font-size: 23px;
    font-weight: 900;
}}
#PortraitBoxEmpty {{
    background: #2b3037;
    color: #8b939c;
    border-style: dashed;
}}
#MiniEquipBox, #MiniEquipBoxMissing {{
    border-radius: 5px;
    border: 1px solid #626b78;
    background: #343a44;
    color: #edf2f5;
    font-size: 10px;
    font-weight: 800;
}}
#MiniEquipBoxMissing {{
    border-color: #b9825f;
    background: #4a382f;
    color: #ffd2ad;
}}
#SlotName {{
    color: #f8f3e7;
    font-weight: 800;
}}
#StatBadge {{
    border-radius: 4px;
    background: #11151b;
    color: #ffffff;
    font-size: 9px;
    font-weight: 900;
}}
#WarningBadge {{
    border-radius: 4px;
    border: 1px solid #b9825f;
    color: #ffd2ad;
    background: #4a382f;
    font-weight: 900;
}}
"""



def _active_draft_summary_lines(
    session: PvpActiveDraftSession,
) -> list[str]:
    board = session.board_dict()
    draft_system = _mapping(board.get("draft_system"))
    requirement = board.get("current_requirement")
    requirement_text = _format_requirement(requirement if isinstance(requirement, Mapping) else None)
    progress = _mapping(board.get("progress"))
    action_log = board.get("action_log")
    action_log_count = len(action_log) if isinstance(action_log, list) else 0
    return [
        tr("app_shell.pvp.play.summary_p1").format(name=session.player_1_deck_name),
        tr("app_shell.pvp.play.summary_p2").format(name=session.player_2_deck_name),
        tr("app_shell.pvp.play.summary_system").format(
            system_id=_text(draft_system.get("system_id")),
        ),
        tr("app_shell.pvp.play.summary_requirement").format(
            requirement=requirement_text,
        ),
        tr("app_shell.pvp.play.summary_legal_targets").format(
            count=int(progress.get("legal_target_count") or 0),
        ),
        tr("app_shell.pvp.play.summary_action_log").format(
            count=action_log_count,
        ),
        tr("app_shell.pvp.play.summary_open_draft"),
    ]


def _draft_is_complete(board: Mapping[str, Any]) -> bool:
    status = _mapping(board.get("status"))
    return bool(status.get("draft_finished")) or board.get("current_requirement") is None


def _draft_action_title(board: Mapping[str, Any]) -> str:
    if _draft_is_complete(board):
        return tr("app_shell.pvp.draft.completed_title")
    requirement = _mapping(board.get("current_requirement"))
    return tr("app_shell.pvp.draft.current_action").format(
        seat=_seat_label(_text(requirement.get("active_seat"))),
        action=_draft_action_label(_text(requirement.get("expected_action_type"))),
    )


def _draft_action_detail(board: Mapping[str, Any]) -> str:
    progress = _mapping(board.get("progress"))
    action_log = board.get("action_log")
    action_log_count = len(action_log) if isinstance(action_log, list) else 0
    return tr("app_shell.pvp.draft.progress_line").format(
        step=int(progress.get("current_step_number") or 0),
        total=int(progress.get("schedule_steps_total") or 0),
        legal=int(progress.get("legal_target_count") or 0),
        actions=int(progress.get("actions_accepted") or action_log_count),
        actions_total=int(progress.get("actions_total_expected") or 0),
    )


def _draft_panel_status_lines(
    board: Mapping[str, Any],
    *,
    stage: str = PVP_DRAFT_STAGE_DRAFT,
    workspace: PvpWorkspace | None = None,
) -> list[str]:
    if stage == PVP_DRAFT_STAGE_ASSIGNMENT and workspace is not None:
        view_state = workspace._draft_view_state()
        return [
            tr("app_shell.pvp.post.stage_assignment"),
            tr("app_shell.pvp.post.assignment_panel_status").format(
                p1=len(_assigned_character_ids(view_state, "player_1")),
                p2=len(_assigned_character_ids(view_state, "player_2")),
            ),
            tr("app_shell.pvp.post.ready_status").format(
                ready=_ready_text(workspace.assignment_ready()),
            ),
        ]
    if stage == PVP_DRAFT_STAGE_WEAPONS and workspace is not None:
        view_state = workspace._draft_view_state()
        return [
            tr("app_shell.pvp.post.stage_weapons"),
            tr("app_shell.pvp.post.weapon_panel_status").format(
                p1=len(_weapon_assignment_map(view_state, "player_1")),
                p2=len(_weapon_assignment_map(view_state, "player_2")),
            ),
            tr("app_shell.pvp.post.ready_status").format(
                ready=_ready_text(workspace.weapons_ready()),
            ),
        ]
    if stage == PVP_DRAFT_STAGE_TIMERS_RESULTS and workspace is not None:
        view_state = workspace._draft_view_state()
        return [
            tr("app_shell.pvp.post.stage_timers"),
            tr("app_shell.pvp.post.timer_panel_status").format(
                p1=_valid_timer_count(view_state, "player_1"),
                p2=_valid_timer_count(view_state, "player_2"),
            ),
            tr("app_shell.pvp.post.timer_total_line").format(
                seat=_seat_label("player_1"),
                total=_format_seconds(_timer_total_seconds(view_state, "player_1")),
            ),
            tr("app_shell.pvp.post.timer_total_line").format(
                seat=_seat_label("player_2"),
                total=_format_seconds(_timer_total_seconds(view_state, "player_2")),
            ),
            tr("app_shell.pvp.post.ready_status").format(
                ready=_ready_text(workspace.timers_ready()),
            ),
        ]
    if stage == PVP_DRAFT_STAGE_COMPLETED_RESULT and workspace is not None:
        result = (
            workspace.active_draft_session.controller.state.match_result
            if workspace.active_draft_session is not None
            else None
        )
        if result is None:
            return [tr("app_shell.pvp.post.stage_result")]
        payload = result.to_dict()
        return [
            tr("app_shell.pvp.post.stage_result"),
            tr("app_shell.pvp.post.result_status").format(
                status=_text(payload.get("status")),
                winner=(
                    _seat_label(_text(payload.get("winner_seat")))
                    if payload.get("winner_seat")
                    else tr("app_shell.pvp.draft.none")
                ),
                diff=int(payload.get("seconds_difference") or 0),
            ),
            tr("app_shell.pvp.post.timer_total_line").format(
                seat=_seat_label("player_1"),
                total=_format_seconds(_mapping(payload.get("totals")).get("player_1")),
            ),
            tr("app_shell.pvp.post.timer_total_line").format(
                seat=_seat_label("player_2"),
                total=_format_seconds(_mapping(payload.get("totals")).get("player_2")),
            ),
        ]

    draft_system = _mapping(board.get("draft_system"))
    progress = _mapping(board.get("progress"))
    requirement = _mapping(board.get("current_requirement"))
    if _draft_is_complete(board):
        requirement_text = tr("app_shell.pvp.draft.completed_title")
    else:
        requirement_text = _format_requirement(requirement)
    return [
        tr("app_shell.pvp.play.summary_system").format(
            system_id=_text(draft_system.get("system_id")),
        ),
        tr("app_shell.pvp.play.summary_requirement").format(
            requirement=requirement_text,
        ),
        tr("app_shell.pvp.play.summary_legal_targets").format(
            count=int(progress.get("legal_target_count") or 0),
        ),
        tr("app_shell.pvp.draft.accepted_actions").format(
            count=int(progress.get("actions_accepted") or 0),
            total=int(progress.get("actions_total_expected") or 0),
        ),
        tr("app_shell.pvp.draft.status").format(
            status=(
                tr("app_shell.pvp.draft.completed")
                if _draft_is_complete(board)
                else tr("app_shell.pvp.draft.in_progress")
            ),
        ),
    ]


def _ready_text(value: bool) -> str:
    return (
        tr("app_shell.pvp.post.ready_yes")
        if value
        else tr("app_shell.pvp.post.ready_no")
    )


def _draft_action_log_lines(
    board: Mapping[str, Any],
    *,
    limit: int,
) -> list[str]:
    action_log = board.get("action_log")
    if not isinstance(action_log, list) or not action_log:
        return [tr("app_shell.pvp.draft.action_log_empty")]
    rows = action_log[-limit:]
    return [
        tr("app_shell.pvp.draft.action_log_row").format(
            index=int(_mapping(row).get("sequence") or _mapping(row).get("index") or 0),
            seat=_seat_label(_text(_mapping(row).get("seat"))),
            action=_draft_action_label(_text(_mapping(row).get("action_type"))),
            target=_text(_mapping(row).get("target_display_name"))
            or _text(_mapping(row).get("target_id")),
        )
        for row in rows
    ]


def _completed_draft_lines(board: Mapping[str, Any]) -> list[str]:
    action_log = board.get("action_log")
    rows = [_mapping(row) for row in action_log] if isinstance(action_log, list) else []
    return [
        tr("app_shell.pvp.draft.final_picks").format(
            seat=_seat_label("player_1"),
            items=_draft_result_zone_text(board, seat="player_1", zone="picked"),
        ),
        tr("app_shell.pvp.draft.final_bans").format(
            seat=_seat_label("player_1"),
            items=_draft_result_zone_text(board, seat="player_1", zone="banned"),
        ),
        tr("app_shell.pvp.draft.final_picks").format(
            seat=_seat_label("player_2"),
            items=_draft_result_zone_text(board, seat="player_2", zone="picked"),
        ),
        tr("app_shell.pvp.draft.final_bans").format(
            seat=_seat_label("player_2"),
            items=_draft_result_zone_text(board, seat="player_2", zone="banned"),
        ),
        tr("app_shell.pvp.play.summary_action_log").format(count=len(rows)),
    ]


def _joined_action_targets(
    rows: list[dict[str, Any]],
    *,
    seat: str,
    action_type: str,
) -> str:
    values = [
        _text(row.get("target_display_name")) or _text(row.get("target_id"))
        for row in rows
        if row.get("seat") == seat and row.get("action_type") == action_type
    ]
    return ", ".join(values) if values else tr("app_shell.pvp.draft.none")


def _unified_pool(board: Mapping[str, Any]) -> Mapping[str, Any]:
    return _mapping(board.get("unified_pool"))


def _unified_pool_entries(board: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    entries = _unified_pool(board).get("entries")
    if not isinstance(entries, list):
        return []
    return [_mapping(entry) for entry in entries]


def _draft_main_pool_entries(board: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return [
        entry
        for entry in _unified_pool_entries(board)
        if _text(entry.get("zone")) == "pool"
    ]


def build_pvp_draft_grid_item(
    entry: Mapping[str, Any],
    *,
    portrait_path: str,
    result_seat: str = "",
    result_zone: str = "",
) -> PixelIconGridItem:
    """Build the shared portrait-first item used by Draft pool and results."""
    character_id = _text(entry.get("character_id"))
    owner_seats = _owner_seats(entry)
    per_seat = _mapping(entry.get("per_seat"))
    legal = bool(entry.get("is_current_legal_target")) and not result_zone
    active_seat = _text(entry.get("active_seat"))
    result_owner = result_seat or _text(entry.get("picked_by")) or _text(entry.get("banned_by"))
    accent_seat = active_seat if legal else result_owner
    player_accent = pvp_player_color(
        accent_seat if accent_seat in PVP_SEATS else "player_1"
    )
    accent = PVP_DRAFT_BAN_ACCENT if result_zone == "banned" else player_accent
    outline = None
    if legal or result_zone:
        outline = PixelIconGridOutline(
            color=accent,
            width=3 if legal else 2,
            radius=5,
            fill_color=accent if legal else "",
            fill_alpha=24 if legal else 0,
        )
    badges: list[PixelIconGridBadge] = []
    if not result_zone:
        for seat, position, color in (
            ("player_1", "bottom_left", pvp_player_color("player_1")),
            ("player_2", "bottom_right", pvp_player_color("player_2")),
        ):
            if seat not in owner_seats:
                continue
            constellation = int(_mapping(per_seat.get(seat)).get("constellation") or 0)
            badges.append(
                PixelIconGridBadge(
                    text=f"C{constellation}",
                    color=color,
                    position=position,
                    width=24,
                    height=18,
                    margin=2,
                    font_size=8,
                )
            )
    status = _text(entry.get("status")) or "available"
    return PixelIconGridItem(
        item_id=character_id,
        icon_path=portrait_path,
        label=_text(entry.get("display_name")) or character_id,
        tooltip=_draft_unified_card_text(entry),
        enabled=legal,
        outline=outline,
        overlay_fill=(
            None
            if legal or result_zone
            else PixelIconGridFill(color=UI_SELECTION_NEUTRAL_FILL, alpha=118)
        ),
        badges=tuple(badges),
        properties={
            "characterId": character_id,
            "status": status,
            "zone": result_zone or _text(entry.get("zone")) or "pool",
            "legalTarget": legal,
            "ownerP1": "player_1" in owner_seats,
            "ownerP2": "player_2" in owner_seats,
            "sharedOwner": len(owner_seats) > 1,
            "hasImage": bool(portrait_path),
            "action": dict(entry.get("action")) if isinstance(entry.get("action"), Mapping) else {},
        },
        pixmap_cache_key_parts=("pvp_draft", character_id),
    )


def _draft_entries_by_id(board: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {
        _text(entry.get("character_id")): entry
        for entry in _unified_pool_entries(board)
        if _text(entry.get("character_id"))
    }


def _owner_seats(entry: Mapping[str, Any]) -> tuple[str, ...]:
    seats = entry.get("owner_seats")
    if not isinstance(seats, list):
        return ()
    return tuple(_text(seat) for seat in seats if _text(seat))


def _draft_unified_pool_summary(
    board: Mapping[str, Any],
    entries: list[Mapping[str, Any]],
) -> str:
    shared_count = sum(1 for entry in entries if len(_owner_seats(entry)) > 1)
    return tr("app_shell.pvp.draft.unified_pool_summary").format(
        pool=len(entries),
        shared=shared_count,
        legal=sum(bool(entry.get("is_current_legal_target")) for entry in entries),
    )


def _draft_unified_card_text(entry: Mapping[str, Any]) -> str:
    name = _text(entry.get("display_name")) or _text(entry.get("character_id"))
    meta = " ".join(
        part
        for part in (
            _text(entry.get("element")),
            _text(entry.get("weapon_type")),
            _level_text(entry.get("level")),
        )
        if part
    )
    ownership = _draft_ownership_text(entry)
    status = _draft_card_status_label(_text(entry.get("status")))
    return "\n".join(part for part in (name, meta, ownership, status) if part)


def _draft_ownership_text(entry: Mapping[str, Any]) -> str:
    per_seat = _mapping(entry.get("per_seat"))
    parts: list[str] = []
    for seat in _owner_seats(entry):
        metadata = _mapping(per_seat.get(seat))
        parts.append(
            f"{_seat_short_label(seat)} {_constellation_text(metadata.get('constellation'))}"
        )
    return " | ".join(parts)


def _seat_short_label(seat: str) -> str:
    if seat == "player_1":
        return "P1"
    if seat == "player_2":
        return "P2"
    return seat


def _draft_action_from_unified_pool(
    board: Mapping[str, Any],
    action_payload: Mapping[str, Any],
) -> tuple[str, str] | None:
    action_type = _text(action_payload.get("type"))
    target_type = _text(action_payload.get("target_type"))
    character_id = _text(action_payload.get("character_id"))
    if (
        action_type not in {"ban_character", "pick_character"}
        or target_type != "character"
        or not character_id
    ):
        return None
    entry = _draft_entries_by_id(board).get(character_id)
    if not entry or not bool(entry.get("is_current_legal_target")):
        return None
    entry_action = _mapping(entry.get("action"))
    if (
        _text(entry_action.get("type")) != action_type
        or _text(entry_action.get("target_type")) != target_type
        or _text(entry_action.get("character_id")) != character_id
    ):
        return None
    return action_type, character_id


def _draft_result_zone_title(seat: str, zone: str) -> str:
    label = tr("app_shell.pvp.draft.picked") if zone == "picked" else tr("app_shell.pvp.draft.banned")
    return f"{_seat_label(seat)} · {label}"


def _draft_result_zone_text(
    board: Mapping[str, Any],
    *,
    seat: str,
    zone: str,
) -> str:
    result_zones = _mapping(_unified_pool(board).get("result_zones"))
    seat_zones = _mapping(result_zones.get(seat))
    character_ids = seat_zones.get(zone)
    if not isinstance(character_ids, list) or not character_ids:
        return tr("app_shell.pvp.draft.none")
    entries_by_id = _draft_entries_by_id(board)
    labels = [
        _draft_entry_display_name(entries_by_id.get(_text(character_id)), _text(character_id))
        for character_id in character_ids
    ]
    return ", ".join(label for label in labels if label) or tr("app_shell.pvp.draft.none")


def _draft_entry_display_name(
    entry: Mapping[str, Any] | None,
    fallback: str,
) -> str:
    if entry is None:
        return fallback
    return _text(entry.get("display_name")) or fallback


def _draft_stage(view_state: Mapping[str, Any]) -> str:
    stage = _text(view_state.get("stage"))
    return stage if stage in PVP_DRAFT_STAGE_VALUES else PVP_DRAFT_STAGE_DRAFT


def _draft_stage_title(board: Mapping[str, Any], stage: str) -> str:
    if stage == PVP_DRAFT_STAGE_ASSIGNMENT:
        return tr("app_shell.pvp.post.assignment_title")
    if stage == PVP_DRAFT_STAGE_WEAPONS:
        return tr("app_shell.pvp.post.weapons_title")
    if stage == PVP_DRAFT_STAGE_TIMERS_RESULTS:
        return tr("app_shell.pvp.post.timers_title")
    if stage == PVP_DRAFT_STAGE_COMPLETED_RESULT:
        return tr("app_shell.pvp.post.result_summary_title")
    return _draft_action_title(board)


def _draft_stage_detail(
    board: Mapping[str, Any],
    stage: str,
    view_state: Mapping[str, Any],
) -> str:
    if stage == PVP_DRAFT_STAGE_ASSIGNMENT:
        return tr("app_shell.pvp.post.assignment_detail").format(
            p1=len(_assigned_character_ids(view_state, "player_1")),
            p2=len(_assigned_character_ids(view_state, "player_2")),
        )
    if stage == PVP_DRAFT_STAGE_WEAPONS:
        return tr("app_shell.pvp.post.weapons_detail").format(
            p1=len(_weapon_assignment_map(view_state, "player_1")),
            p2=len(_weapon_assignment_map(view_state, "player_2")),
        )
    if stage == PVP_DRAFT_STAGE_TIMERS_RESULTS:
        return tr("app_shell.pvp.post.timers_detail").format(
            p1=_valid_timer_count(view_state, "player_1"),
            p2=_valid_timer_count(view_state, "player_2"),
        )
    if stage == PVP_DRAFT_STAGE_COMPLETED_RESULT:
        return tr("app_shell.pvp.post.result_detail")
    return _draft_action_detail(board)


def _assignment_slots(
    view_state: Mapping[str, Any],
    seat: str,
) -> list[list[str | None]]:
    slots = [[None for _slot in range(4)] for _team in range(2)]
    source = _mapping(view_state.get("assignment_slots")).get(seat)
    if not isinstance(source, list):
        return slots
    for team_index, team_value in enumerate(source[:2]):
        if not isinstance(team_value, list):
            continue
        for slot_index, character_id in enumerate(team_value[:4]):
            text = _text(character_id)
            slots[team_index][slot_index] = text or None
    return slots


def _assigned_character_ids(
    view_state: Mapping[str, Any],
    seat: str,
) -> tuple[str, ...]:
    return tuple(
        character_id
        for team in _assignment_slots(view_state, seat)
        for character_id in team
        if character_id
    )


def _picked_character_ids(board: Mapping[str, Any], seat: str) -> tuple[str, ...]:
    result_zones = _mapping(_unified_pool(board).get("result_zones"))
    picked = _mapping(result_zones.get(seat)).get("picked")
    if not isinstance(picked, list):
        return ()
    return tuple(_text(character_id) for character_id in picked if _text(character_id))


def _entry_display_name_for_id(board: Mapping[str, Any], character_id: str) -> str:
    return _draft_entry_display_name(
        _draft_entries_by_id(board).get(character_id),
        character_id,
    )


def _weapon_assignment_map(
    view_state: Mapping[str, Any],
    seat: str,
) -> dict[str, str]:
    values = _mapping(_mapping(view_state.get("weapon_assignments")).get(seat))
    return {
        _text(character_id): _text(stack_key)
        for character_id, stack_key in values.items()
        if _text(character_id) and _text(stack_key)
    }


def _compatible_weapon_stacks(
    session: PvpActiveDraftSession,
    seat: str,
    character_id: str,
) -> tuple[Any, ...]:
    try:
        deck = session.controller.session_state.deck_for(seat)
    except Exception:
        return ()
    character = deck.character_by_id.get(character_id)
    if character is None:
        return ()
    character_weapon_type = _filter_token(character.weapon_type)
    stacks = [
        stack
        for stack in deck.weapons
        if _filter_token(stack.weapon_type) == character_weapon_type
    ]
    return tuple(
        sorted(
            stacks,
            key=lambda stack: (
                stack.display_name.casefold(),
                -(stack.rarity or 0),
                -(stack.level or 0),
                -(stack.refinement or 0),
                stack.stack_key,
            ),
        )
    )


def _weapon_stack_remaining(
    session: PvpActiveDraftSession,
    view_state: Mapping[str, Any],
    seat: str,
    stack_key: str,
    *,
    selected_character_id: str = "",
) -> int:
    try:
        deck = session.controller.session_state.deck_for(seat)
    except Exception:
        return 0
    stack = deck.weapon_stack_by_key.get(stack_key)
    if stack is None:
        return 0
    available = max(0, int(stack.count or 0))
    used = sum(
        1
        for character_id, assigned_stack_key in _weapon_assignment_map(
            view_state,
            seat,
        ).items()
        if assigned_stack_key == stack_key and character_id != selected_character_id
    )
    return max(0, available - used)


def _weapon_stack_is_assignable(
    session: PvpActiveDraftSession,
    view_state: Mapping[str, Any],
    seat: str,
    character_id: str,
    stack_key: str,
) -> bool:
    if character_id not in set(_assigned_character_ids(view_state, seat)):
        return False
    try:
        deck = session.controller.session_state.deck_for(seat)
    except Exception:
        return False
    character = deck.character_by_id.get(character_id)
    stack = deck.weapon_stack_by_key.get(stack_key)
    if character is None or stack is None:
        return False
    if _filter_token(character.weapon_type) != _filter_token(stack.weapon_type):
        return False
    return _weapon_stack_remaining(
        session,
        view_state,
        seat,
        stack_key,
        selected_character_id=character_id,
    ) > 0


def _weapon_display_name(
    session: PvpActiveDraftSession,
    seat: str,
    stack_key: str,
) -> str:
    if not stack_key:
        return ""
    try:
        deck = session.controller.session_state.deck_for(seat)
    except Exception:
        return ""
    stack = deck.weapon_stack_by_key.get(stack_key)
    return stack.display_name if stack is not None else stack_key


def _timer_text(view_state: Mapping[str, Any], seat: str, index: int) -> str:
    values = _mapping(view_state.get("timer_texts")).get(seat)
    if not isinstance(values, list) or not (0 <= index < len(values)):
        return ""
    return _text(values[index])


def _parse_timer_text(text: str) -> int | None:
    value = _text(text)
    if not value:
        return None
    if ":" not in value:
        try:
            seconds = int(value)
        except ValueError:
            return None
        return seconds if seconds >= 0 else None
    parts = value.split(":")
    if len(parts) != 2:
        return None
    minutes_text, seconds_text = parts
    if not minutes_text.isdigit() or not seconds_text.isdigit():
        return None
    minutes = int(minutes_text)
    seconds = int(seconds_text)
    if seconds >= 60:
        return None
    return minutes * 60 + seconds


def _parse_pvp_remaining_timer_text(text: str) -> int | None:
    seconds = _parse_timer_text(text)
    if seconds is None:
        return None
    if not ABYSS_TIMER_EDIT_MIN_SECONDS <= seconds <= ABYSS_CHAMBER_START_SECONDS:
        return None
    return seconds


def _timer_total_seconds(view_state: Mapping[str, Any], seat: str) -> int:
    total = 0
    for index in range(len(PVP_TIMER_CHAMBERS)):
        remaining = _parse_pvp_remaining_timer_text(_timer_text(view_state, seat, index))
        if remaining is not None:
            total += ABYSS_CHAMBER_START_SECONDS - remaining
    return total


def _valid_timer_count(view_state: Mapping[str, Any], seat: str) -> int:
    return sum(
        1
        for index in range(len(PVP_TIMER_CHAMBERS))
        if _parse_pvp_remaining_timer_text(_timer_text(view_state, seat, index)) is not None
    )


def _format_seconds(value: Any) -> str:
    try:
        seconds = max(0, int(value or 0))
    except (TypeError, ValueError):
        seconds = 0
    minutes, remainder = divmod(seconds, 60)
    return f"{minutes:02d}:{remainder:02d}"


def _post_draft_team_weapon_summary(
    session: PvpActiveDraftSession | None,
    board: Mapping[str, Any],
    seat: str,
) -> str:
    if session is None:
        return ""
    state = session.controller.state
    team_assignment = state.team_assignments.get(seat)
    if team_assignment is None:
        return tr("app_shell.pvp.post.team_summary_missing").format(
            seat=_seat_label(seat),
        )
    weapon_assignment = state.weapon_assignments.get(seat)
    weapon_by_character = {
        assignment.character_id: assignment.weapon_stack_key
        for assignment in (weapon_assignment.assignments if weapon_assignment else ())
    }
    try:
        deck = session.controller.session_state.deck_for(seat)
    except Exception:
        deck = None
    team_parts: list[str] = []
    for team in sorted(team_assignment.teams, key=lambda item: item.team_index):
        character_parts: list[str] = []
        for character_id in team.character_ids:
            character_name = _entry_display_name_for_id(board, character_id)
            stack_key = weapon_by_character.get(character_id, "")
            weapon_name = ""
            if deck is not None and stack_key:
                stack = deck.weapon_stack_by_key.get(stack_key)
                weapon_name = stack.display_name if stack is not None else stack_key
            character_parts.append(
                f"{character_name} ({weapon_name or tr('app_shell.pvp.draft.none')})"
            )
        team_parts.append(
            tr("app_shell.pvp.post.team_summary_team").format(
                index=team.team_index + 1,
                characters=", ".join(character_parts)
                or tr("app_shell.pvp.draft.none"),
            )
        )
    return tr("app_shell.pvp.post.team_summary").format(
        seat=_seat_label(seat),
        teams=" | ".join(team_parts),
    )


def _result_chamber_timer_lines(payload: Mapping[str, Any]) -> list[str]:
    lines: list[str] = []
    for seat, timer_key in (
        ("player_1", "player_1_timers"),
        ("player_2", "player_2_timers"),
    ):
        chambers = _mapping(payload.get(timer_key)).get("chambers")
        if not isinstance(chambers, list):
            continue
        for index, chamber_value in enumerate(chambers):
            chamber = _mapping(chamber_value)
            chamber_id = _text(chamber.get("chamber_id")) or str(index + 1)
            seconds = chamber.get("normalized_elapsed_seconds")
            if seconds is None:
                seconds = chamber.get("elapsed_seconds")
            lines.append(
                tr("app_shell.pvp.post.timer_chamber_line").format(
                    seat=_seat_label(seat),
                    chamber=chamber_id,
                    total=_format_seconds(seconds),
                )
            )
    return lines


def _is_post_draft_stage(stage: str) -> bool:
    return stage in {
        PVP_DRAFT_STAGE_ASSIGNMENT,
        PVP_DRAFT_STAGE_WEAPONS,
        PVP_DRAFT_STAGE_TIMERS_RESULTS,
        PVP_DRAFT_STAGE_COMPLETED_RESULT,
    }


def _postdraft_source_object_name(seat: str) -> str:
    if seat == "player_1":
        return "pvp-postdraft-source-player-1"
    return "pvp-postdraft-source-player-2"


def _postdraft_target_object_name(seat: str) -> str:
    if seat == "player_1":
        return "pvp-postdraft-target-player-1"
    return "pvp-postdraft-target-player-2"


def _character_assets_by_id(
    assets: Iterable[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for asset in assets:
        character_id = character_id_from_asset(asset)
        if character_id:
            result[character_id] = dict(asset)
    return result


def _weapon_assets_by_stack_key(
    assets: Iterable[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for asset in assets:
        weapon_ref = weapon_ref_from_asset(asset)
        if weapon_ref is not None and weapon_ref.key:
            result[weapon_ref.key] = dict(asset)
            metadata = _mapping(asset.get("metadata"))
            weapon = _mapping(metadata.get("weapon"))
            for weapon_type in (
                weapon_ref.weapon_type,
                weapon.get("weapon_type_name"),
                weapon.get("type_name"),
                weapon.get("type"),
            ):
                fallback_key = weapon_observed_stack_key(
                    weapon_id=weapon_ref.weapon_id,
                    weapon_type=weapon_type,
                    rarity=weapon_ref.rarity,
                    level=weapon_ref.level,
                    refinement=weapon_ref.refinement,
                )
                if fallback_key:
                    result.setdefault(fallback_key, dict(asset))
    return result


def _asset_image_path(asset: Mapping[str, Any] | None) -> str:
    if asset is None:
        return ""
    metadata = _mapping(asset.get("metadata"))
    character = _mapping(metadata.get("character"))
    weapon = _mapping(metadata.get("weapon"))
    for value in (
        character.get("portrait_path"),
        character.get("local_portrait_path"),
        character.get("side_icon_path"),
        character.get("icon_path"),
        weapon.get("icon_path"),
        weapon.get("local_icon_path"),
        asset.get("path"),
    ):
        path = _existing_local_asset_path(value)
        if path:
            return path
    return ""


def _existing_local_asset_path(value: Any) -> str:
    path_text = _text(value)
    if not path_text:
        return ""
    path = Path(path_text)
    candidates = [path]
    if not path.is_absolute():
        candidates.append(PVP_BROWSER_PROJECT_ROOT / path)
    for candidate in candidates:
        try:
            if candidate.is_file():
                return str(candidate)
        except OSError:
            continue
    return ""


def _postdraft_grid_scroll_area(
    grid: PixelIconGrid,
    *,
    object_name: str,
    maximum_height: int,
) -> OverlayVerticalScrollArea:
    scroll = OverlayVerticalScrollArea()
    scroll.setObjectName(object_name)
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.viewport().setObjectName("pvp-postdraft-source-grid-viewport")
    content = QWidget()
    content.setObjectName("pvp-postdraft-source-grid-content")
    layout = QVBoxLayout(content)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)
    layout.addWidget(grid)
    scroll.setWidget(content)
    scroll.setMaximumHeight(maximum_height)
    scroll.setMinimumHeight(min(maximum_height, max(1, grid.minimumSizeHint().height() + 4)))
    return scroll


def _postdraft_character_tooltip(name: str, *, assigned: bool) -> str:
    lines = [_text(name)]
    if assigned:
        lines.append(tr("app_shell.pvp.post.assigned_marker"))
    return "\n".join(line for line in lines if line)


def _postdraft_weapon_tooltip(
    session: PvpActiveDraftSession,
    seat: str,
    stack_key: str,
) -> str:
    if not stack_key:
        return ""
    try:
        stack = session.controller.session_state.deck_for(seat).weapon_stack_by_key.get(stack_key)
    except Exception:
        stack = None
    if stack is None:
        return stack_key
    parts = [stack.display_name or stack_key]
    meta: list[str] = []
    if stack.refinement is not None:
        meta.append(f"R{stack.refinement}")
    if stack.level is not None:
        meta.append(f"Lv.{stack.level}")
    if stack.count:
        meta.append(f"x{stack.count}")
    if meta:
        parts.append(" | ".join(meta))
    return "\n".join(part for part in parts if part)


def _postdraft_timer_total(
    session: PvpActiveDraftSession,
    view_state: Mapping[str, Any],
    seat: str,
) -> int:
    result = session.controller.state.match_result
    if result is not None:
        return int(_mapping(result.to_dict().get("totals")).get(seat) or 0)
    return _timer_total_seconds(view_state, seat)


def _completed_timer_text(
    session: PvpActiveDraftSession,
    seat: str,
    index: int,
) -> str:
    result = session.controller.state.match_result
    if result is None:
        return "--:--"
    timer_key = "player_1_timers" if seat == "player_1" else "player_2_timers"
    chambers = _mapping(result.to_dict().get(timer_key)).get("chambers")
    if not isinstance(chambers, list) or not (0 <= index < len(chambers)):
        return "--:--"
    chamber = _mapping(chambers[index])
    seconds = chamber.get("normalized_elapsed_seconds")
    if seconds is None:
        seconds = chamber.get("elapsed_seconds")
    return _format_seconds(seconds)


def _result_line_for_seat(session: PvpActiveDraftSession, seat: str) -> str:
    result = session.controller.state.match_result
    if result is None:
        return ""
    payload = result.to_dict()
    winner = _text(payload.get("winner_seat"))
    if not winner:
        outcome = tr("app_shell.pvp.post.result_draw")
    elif winner == seat:
        outcome = tr("app_shell.pvp.post.result_win")
    else:
        outcome = tr("app_shell.pvp.post.result_loss")
    return tr("app_shell.pvp.post.result_seat_line").format(
        result=outcome,
        diff=int(payload.get("seconds_difference") or 0),
    )


def _is_legal_card(board: Mapping[str, Any], seat: str, character_id: str) -> bool:
    seats = _mapping(board.get("seats"))
    seat_board = _mapping(seats.get(seat))
    cards = seat_board.get("cards")
    if not isinstance(cards, list):
        return False
    for card_value in cards:
        card = _mapping(card_value)
        if _text(card.get("character_id")) == character_id:
            return bool(card.get("is_current_legal_target"))
    return False


def _draft_card_text(card: Mapping[str, Any]) -> str:
    name = _text(card.get("display_name")) or _text(card.get("character_id"))
    meta = " ".join(
        part
        for part in (
            _text(card.get("element")),
            _text(card.get("weapon_type")),
            _level_text(card.get("level")),
            _constellation_text(card.get("constellation")),
        )
        if part
    )
    status = _draft_card_status_label(_text(card.get("status")))
    return "\n".join(part for part in (name, meta, status) if part)


def _seat_title(seat: str, seat_board: Mapping[str, Any]) -> str:
    deck = _mapping(seat_board.get("deck"))
    nickname = _text(seat_board.get("nickname"))
    deck_name = _text(deck.get("deck_name"))
    return tr("app_shell.pvp.draft.seat_title").format(
        seat=_seat_label(seat),
        nickname=nickname or _seat_label(seat),
        deck=deck_name,
    )


def _seat_is_active(seat_board: Mapping[str, Any]) -> bool:
    cards = seat_board.get("cards")
    if not isinstance(cards, list):
        return False
    return any(bool(_mapping(card).get("is_active_seat_card")) for card in cards)


def _seat_label(seat: str) -> str:
    if seat == "player_1":
        return tr("app_shell.pvp.draft.player_1")
    if seat == "player_2":
        return tr("app_shell.pvp.draft.player_2")
    return seat


def _draft_action_label(action_type: str) -> str:
    if action_type == "pick_character":
        return tr("app_shell.pvp.draft.pick")
    if action_type == "ban_character":
        return tr("app_shell.pvp.draft.ban")
    return action_type


def _draft_card_status_label(status: str) -> str:
    labels = {
        "available": tr("app_shell.pvp.draft.available"),
        "legal_target": tr("app_shell.pvp.draft.legal_target"),
        "globally_banned": tr("app_shell.pvp.draft.banned"),
        "picked_by_self": tr("app_shell.pvp.draft.picked"),
        "picked_by_opponent": tr("app_shell.pvp.draft.picked"),
        "blocked_by_opponent_pick": tr("app_shell.pvp.draft.blocked"),
        "picked": tr("app_shell.pvp.draft.picked"),
        "banned": tr("app_shell.pvp.draft.banned"),
        "blocked": tr("app_shell.pvp.draft.blocked"),
        "unavailable": tr("app_shell.pvp.draft.unavailable"),
        "invalid": tr("app_shell.pvp.draft.invalid"),
        "unsupported_traveler": tr("app_shell.pvp.draft.invalid"),
    }
    return labels.get(status, status)


def _level_text(value: Any) -> str:
    level = int(value or 0)
    return f"Lv.{level}" if level else ""


def _constellation_text(value: Any) -> str:
    constellation = int(value or 0)
    return f"C{constellation}" if constellation else "C0"


def _format_requirement(requirement: Mapping[str, Any] | None) -> str:
    if not requirement:
        return tr("app_shell.pvp.play.requirement_none")
    parts = [
        _text(requirement.get("phase")),
        _text(requirement.get("active_seat")),
        _text(requirement.get("expected_action_type")),
    ]
    return " / ".join(part for part in parts if part)


def _compact_issue_codes(codes: tuple[str, ...]) -> str:
    if not codes:
        return ""
    visible = ", ".join(codes[:4])
    if len(codes) > 4:
        visible += ", ..."
    return f": {visible}"


def _clear_grid(grid: QGridLayout) -> None:
    while grid.count():
        item = grid.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.deleteLater()


def _clear_layout(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        child_layout = item.layout()
        widget = item.widget()
        if child_layout is not None:
            _clear_layout(child_layout)
        if widget is not None:
            widget.deleteLater()


def _reset_grid_columns(grid: QGridLayout) -> None:
    for column in range(grid.columnCount()):
        grid.setColumnMinimumWidth(column, 0)
        grid.setColumnStretch(column, 0)


def _pvp_deck_outline(
    *,
    editing: bool,
    selected: bool,
) -> PixelIconGridOutline | None:
    if not editing or not selected:
        return None
    return PixelIconGridOutline(
        color="#d6b15d",
        width=2,
        radius=4,
        alpha=255,
    )


def _pvp_deck_inactive_fill(
    *,
    editing: bool,
    selected: bool,
) -> PixelIconGridFill | None:
    if not editing or selected:
        return None
    return PixelIconGridFill(color="#0f172a", alpha=132)


def _pvp_deck_item_properties(
    *,
    editing: bool,
    selected: bool,
) -> dict[str, bool]:
    return {
        "deckSelected": bool(selected),
        "deckInactive": bool(editing and not selected),
        "deckEditing": bool(editing),
        "deckEditSelected": bool(editing and selected),
    }


def _weapon_type_filter_keys(weapon: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    for numeric_key in ("weapon_type", "type"):
        weapon_type_id = _optional_int(weapon.get(numeric_key))
        if weapon_type_id is not None:
            filter_key = WEAPON_TYPE_FILTER_BY_ID.get(weapon_type_id)
            if filter_key:
                keys.add(filter_key)
    for text_key in ("weapon_type_name", "type_name", "type"):
        token = _filter_token(weapon.get(text_key))
        if not token:
            continue
        filter_key = WEAPON_TYPE_FILTER_ALIASES.get(token)
        if filter_key:
            keys.add(filter_key)
    return keys


def _filter_token(value: Any) -> str:
    return (
        _text(value)
        .casefold()
        .replace("-", "_")
        .replace(" ", "_")
        .replace("__", "_")
    )


def _pvp_weapon_sort_key(asset: dict[str, Any]):
    metadata = asset.get("metadata") or {}
    weapon = metadata.get("weapon") or {}
    rarity = metadata_int(weapon.get("rarity"))
    level = metadata_int(weapon.get("level"))
    name = _text(weapon.get("name") or metadata.get("name") or asset.get("filename"))
    key = _text(weapon.get("source_key") or weapon.get("weapon_fingerprint"))
    return (-rarity, -level, name.casefold(), key)


def _optional_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _refresh_qss(widget: QWidget) -> None:
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


__all__ = [name for name in globals() if not name.startswith("__")]
