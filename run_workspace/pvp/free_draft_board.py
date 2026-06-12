"""UI-facing Free Draft v0 board/read-model projection.

This module derives a compact board view from the existing Free Draft
controller and reducer state. It intentionally does not own draft rules,
schedule execution, deck loading, UI widgets, or persistence.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Mapping

from .deck import DraftCharacter, DraftDeck
from .schedule import (
    ACTION_BAN_CHARACTER,
    ACTION_PICK_CHARACTER,
    PVP_SEATS,
    SEAT_PLAYER_1,
    SEAT_PLAYER_2,
)
from .session import (
    REJECT_CHARACTER_GLOBALLY_BANNED,
    REJECT_CHARACTER_PICKED_BY_SELF,
    REJECT_CHARACTER_UNAVAILABLE_TO_OPPONENT,
    DraftAction,
    DraftSessionState,
    PlayerTeamAssignment,
    PlayerWeaponAssignment,
    validate_team_assignment,
    validate_weapon_assignment,
)
from .validation import (
    ISSUE_MISSING_CHARACTER_DISPLAY_NAME,
    ISSUE_MISSING_CHARACTER_ID,
    ISSUE_MISSING_CHARACTER_WEAPON_TYPE,
    ISSUE_UNSUPPORTED_TRAVELER_CHARACTER,
    DeckValidationReport,
    UNSUPPORTED_TRAVELER_CHARACTER_IDS,
)

if TYPE_CHECKING:
    from .free_draft_controller import FreeDraftController


CARD_STATUS_AVAILABLE = "available"
CARD_STATUS_LEGAL_TARGET = "legal_target"
CARD_STATUS_GLOBALLY_BANNED = "globally_banned"
CARD_STATUS_PICKED_BY_SELF = "picked_by_self"
CARD_STATUS_PICKED_BY_OPPONENT = "picked_by_opponent"
CARD_STATUS_BLOCKED_BY_OPPONENT_PICK = "blocked_by_opponent_pick"
CARD_STATUS_UNAVAILABLE = "unavailable"
CARD_STATUS_INVALID = "invalid"
CARD_STATUS_UNSUPPORTED_TRAVELER = "unsupported_traveler"

TIMELINE_STATUS_PENDING = "pending"
TIMELINE_STATUS_ACTIVE = "active"
TIMELINE_STATUS_COMPLETE = "complete"

CARD_STATUS_VALUES = (
    CARD_STATUS_AVAILABLE,
    CARD_STATUS_LEGAL_TARGET,
    CARD_STATUS_GLOBALLY_BANNED,
    CARD_STATUS_PICKED_BY_SELF,
    CARD_STATUS_PICKED_BY_OPPONENT,
    CARD_STATUS_BLOCKED_BY_OPPONENT_PICK,
    CARD_STATUS_UNAVAILABLE,
    CARD_STATUS_INVALID,
    CARD_STATUS_UNSUPPORTED_TRAVELER,
)
TIMELINE_STATUS_VALUES = (
    TIMELINE_STATUS_PENDING,
    TIMELINE_STATUS_ACTIVE,
    TIMELINE_STATUS_COMPLETE,
)
REQUIRED_BOARD_PROJECTION_KEYS = (
    "variant",
    "draft_system",
    "status",
    "current_requirement",
    "progress",
    "seats",
    "global_pools",
    "action_log",
    "timeline",
    "summary",
    "issue_codes",
)
FORBIDDEN_BOARD_PROJECTION_TOKENS = (
    "artifact",
    "auth",
    "cookie",
    "local_path",
    "raw_account",
    "raw_dump",
    "row_id",
    "sqlite",
)


@dataclass(frozen=True, slots=True)
class FreeDraftBoardCard:
    character_id: str
    display_name: str
    element: str
    weapon_type: str
    rarity: int | None
    level: int | None
    constellation: int | None
    status: str
    status_reason_codes: tuple[str, ...]
    is_current_legal_target: bool
    is_active_seat_card: bool
    picked_by: str | None = None
    banned_by: str | None = None
    action_index: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "character_id": self.character_id,
            "display_name": self.display_name,
            "element": self.element,
            "weapon_type": self.weapon_type,
            "rarity": self.rarity,
            "level": self.level,
            "constellation": self.constellation,
            "status": self.status,
            "status_reason_codes": list(self.status_reason_codes),
            "is_current_legal_target": self.is_current_legal_target,
            "is_active_seat_card": self.is_active_seat_card,
            "picked_by": self.picked_by,
            "banned_by": self.banned_by,
            "action_index": self.action_index,
        }


@dataclass(frozen=True, slots=True)
class FreeDraftBoardSeat:
    seat: str
    nickname: str
    deck: Mapping[str, Any]
    cards: tuple[FreeDraftBoardCard, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "seat": self.seat,
            "nickname": self.nickname,
            "deck": dict(self.deck),
            "cards": [card.to_dict() for card in self.cards],
        }


@dataclass(frozen=True, slots=True)
class FreeDraftTimelineStep:
    step_index: int
    phase: str
    seat: str
    required_actions: tuple[str, ...]
    status: str
    actions_done: int
    actions_total: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_index": self.step_index,
            "phase": self.phase,
            "seat": self.seat,
            "required_actions": list(self.required_actions),
            "status": self.status,
            "actions_done": self.actions_done,
            "actions_total": self.actions_total,
        }


@dataclass(frozen=True, slots=True)
class FreeDraftActionLogRow:
    index: int
    phase: str
    seat: str
    action_type: str
    target_id: str
    target_display_name: str
    accepted: bool
    step_index: int | None = None
    action_index: int | None = None
    sequence: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "phase": self.phase,
            "seat": self.seat,
            "action_type": self.action_type,
            "target_id": self.target_id,
            "target_display_name": self.target_display_name,
            "accepted": self.accepted,
            "step_index": self.step_index,
            "action_index": self.action_index,
            "sequence": self.sequence,
        }


@dataclass(frozen=True, slots=True)
class FreeDraftBoardProjection:
    variant: str
    draft_system: Mapping[str, Any]
    status: Mapping[str, Any]
    current_requirement: Mapping[str, Any] | None
    progress: Mapping[str, Any]
    seats: Mapping[str, FreeDraftBoardSeat]
    global_pools: Mapping[str, Any]
    action_log: tuple[FreeDraftActionLogRow, ...]
    timeline: tuple[FreeDraftTimelineStep, ...]
    summary: Mapping[str, Any]
    issue_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "variant": self.variant,
            "draft_system": dict(self.draft_system),
            "status": _plain_mapping(self.status),
            "current_requirement": (
                dict(self.current_requirement)
                if self.current_requirement is not None
                else None
            ),
            "progress": _plain_mapping(self.progress),
            "seats": {
                seat: board_seat.to_dict()
                for seat, board_seat in self.seats.items()
            },
            "global_pools": _plain_mapping(self.global_pools),
            "action_log": [row.to_dict() for row in self.action_log],
            "timeline": [step.to_dict() for step in self.timeline],
            "summary": _plain_mapping(self.summary),
            "issue_codes": list(self.issue_codes),
        }


@dataclass(frozen=True, slots=True)
class _ActionMeta:
    log_index: int
    phase: str
    seat: str
    action_type: str
    target_id: str
    target_display_name: str
    step_index: int | None
    step_action_index: int | None
    sequence: int | None


def build_free_draft_board_projection(
    controller: "FreeDraftController",
    *,
    debug: bool = False,
) -> FreeDraftBoardProjection:
    state = controller.session_state
    decks = controller.state.decks_by_seat()
    validations = controller.state.validation_by_seat()
    legal_targets = controller.get_legal_targets(include_excluded=debug)
    legal_target_ids = {
        target.character_id
        for target in legal_targets
        if target.character_id and target.status == "legal"
    }
    excluded_reasons = _excluded_reasons_by_character_id(legal_targets)
    action_metas = _action_metas(state, decks)
    banned_meta_by_id = {
        item.target_id: item
        for item in action_metas
        if item.action_type == ACTION_BAN_CHARACTER and item.target_id
    }
    pick_meta_by_seat = {
        seat: {
            item.target_id: item
            for item in action_metas
            if item.action_type == ACTION_PICK_CHARACTER
            and item.seat == seat
            and item.target_id
        }
        for seat in PVP_SEATS
    }
    seats = {
        seat: _board_seat(
            state,
            seat,
            decks[seat],
            validations[seat],
            legal_target_ids=legal_target_ids,
            excluded_reasons=excluded_reasons,
            banned_meta_by_id=banned_meta_by_id,
            pick_meta_by_seat=pick_meta_by_seat,
            debug=debug,
        )
        for seat in PVP_SEATS
    }
    status = _status_dict(controller, bundle_ready=_bundle_ready(controller))
    progress = _progress_dict(state, legal_target_count=len(legal_target_ids))
    return FreeDraftBoardProjection(
        variant="debug" if debug else "compact",
        draft_system=_draft_system_dict(controller),
        status=status,
        current_requirement=_current_requirement_dict(state),
        progress=progress,
        seats=seats,
        global_pools=_global_pools_dict(state, banned_meta_by_id),
        action_log=tuple(_action_log_row(item) for item in action_metas),
        timeline=_timeline(state),
        summary=_summary_dict(controller),
        issue_codes=controller.issue_codes(),
    )


def validate_free_draft_board_projection_dict(
    payload: Mapping[str, Any],
) -> tuple[str, ...]:
    issues: list[str] = []
    for key in REQUIRED_BOARD_PROJECTION_KEYS:
        if key not in payload:
            issues.append(f"missing_top_level:{key}")

    seats = payload.get("seats")
    if isinstance(seats, Mapping):
        for seat, seat_payload in seats.items():
            if not isinstance(seat_payload, Mapping):
                issues.append(f"seat_not_object:{seat}")
                continue
            cards = seat_payload.get("cards")
            if not isinstance(cards, list):
                issues.append(f"seat_cards_not_list:{seat}")
                continue
            for index, card in enumerate(cards):
                if not isinstance(card, Mapping):
                    issues.append(f"card_not_object:{seat}:{index}")
                    continue
                status = card.get("status")
                if status not in CARD_STATUS_VALUES:
                    issues.append(f"unknown_card_status:{seat}:{index}:{status}")

    timeline = payload.get("timeline")
    if isinstance(timeline, list):
        for index, step in enumerate(timeline):
            if not isinstance(step, Mapping):
                issues.append(f"timeline_step_not_object:{index}")
                continue
            status = step.get("status")
            if status not in TIMELINE_STATUS_VALUES:
                issues.append(f"unknown_timeline_status:{index}:{status}")

    _append_forbidden_token_issues(payload, "$", issues)
    return tuple(dict.fromkeys(issues))


def _draft_system_dict(controller: "FreeDraftController") -> dict[str, Any]:
    system = controller.state.draft_system
    return {
        "system_id": system.system_id,
        "version": system.version,
        "display_name": system.display_name,
    }


def _status_dict(
    controller: "FreeDraftController",
    *,
    bundle_ready: bool,
) -> dict[str, Any]:
    assignments_ready = _assignments_ready(controller)
    return {
        "setup_ready": controller.state.setup_ready,
        "draft_started": bool(controller.accepted_actions),
        "draft_finished": controller.session_state.is_complete,
        "assignments_ready": assignments_ready,
        "result_ready": controller.state.match_result is not None,
        "bundle_ready": bundle_ready,
        "issue_codes": list(controller.issue_codes()),
    }


def _current_requirement_dict(state: DraftSessionState) -> dict[str, Any] | None:
    if state.is_complete:
        return None
    requirement = state.current_requirement
    if requirement is None:
        return None
    step = state.schedule.steps[state.step_index]
    return {
        "phase": step.phase,
        "step_index": state.step_index,
        "action_index": state.action_index,
        "active_seat": step.seat,
        "expected_action_type": requirement.action_type,
        "step_actions_total": len(step.actions),
        "step_actions_done": state.action_index,
    }


def _progress_dict(
    state: DraftSessionState,
    *,
    legal_target_count: int,
) -> dict[str, Any]:
    expected_counts = state.schedule.expected_action_counts()
    steps_total = len(state.schedule.steps)
    return {
        "schedule_steps_total": steps_total,
        "current_step_number": min(state.step_index + 1, steps_total)
        if steps_total
        else 0,
        "actions_total_expected": _expected_action_total(state),
        "actions_accepted": len(state.accepted_actions),
        "legal_target_count": legal_target_count,
        "per_seat": {
            seat: {
                "expected_bans": expected_counts[seat].get(ACTION_BAN_CHARACTER, 0),
                "actual_bans": len(state.banned_character_ids_for(seat)),
                "expected_picks": expected_counts[seat].get(ACTION_PICK_CHARACTER, 0),
                "actual_picks": len(state.picked_character_ids_for(seat)),
            }
            for seat in PVP_SEATS
        },
    }


def _board_seat(
    state: DraftSessionState,
    seat: str,
    deck: DraftDeck,
    validation: DeckValidationReport,
    *,
    legal_target_ids: set[str],
    excluded_reasons: Mapping[str, tuple[str, ...]],
    banned_meta_by_id: Mapping[str, _ActionMeta],
    pick_meta_by_seat: Mapping[str, Mapping[str, _ActionMeta]],
    debug: bool,
) -> FreeDraftBoardSeat:
    return FreeDraftBoardSeat(
        seat=seat,
        nickname=deck.player.nickname,
        deck=_deck_summary(deck, validation),
        cards=tuple(
            _board_card(
                state,
                seat,
                character,
                legal_target_ids=legal_target_ids,
                excluded_reasons=excluded_reasons,
                banned_meta_by_id=banned_meta_by_id,
                pick_meta_by_seat=pick_meta_by_seat,
                debug=debug,
            )
            for character in deck.characters
        ),
    )


def _deck_summary(
    deck: DraftDeck,
    validation: DeckValidationReport,
) -> dict[str, Any]:
    return {
        "deck_name": deck.deck_name,
        "character_count": len(deck.characters),
        "weapon_stack_count": len(deck.weapons),
        "validation_status": validation.status,
        "validation_issue_codes": list(validation.issue_codes()),
    }


def _board_card(
    state: DraftSessionState,
    seat: str,
    character: DraftCharacter,
    *,
    legal_target_ids: set[str],
    excluded_reasons: Mapping[str, tuple[str, ...]],
    banned_meta_by_id: Mapping[str, _ActionMeta],
    pick_meta_by_seat: Mapping[str, Mapping[str, _ActionMeta]],
    debug: bool,
) -> FreeDraftBoardCard:
    character_id = character.character_id
    opponent = state.opponent_seat(seat)
    own_pick_meta = pick_meta_by_seat[seat].get(character_id)
    opponent_pick_meta = pick_meta_by_seat[opponent].get(character_id)
    ban_meta = banned_meta_by_id.get(character_id)
    invalid_reasons = _invalid_character_reason_codes(character)
    is_legal = character_id in legal_target_ids
    reasons: list[str] = []
    picked_by = None
    banned_by = None
    action_index = None

    if _is_unsupported_traveler(character):
        status = CARD_STATUS_UNSUPPORTED_TRAVELER
        reasons.append(ISSUE_UNSUPPORTED_TRAVELER_CHARACTER)
    elif invalid_reasons:
        status = CARD_STATUS_INVALID
        reasons.extend(invalid_reasons)
    elif ban_meta is not None:
        status = CARD_STATUS_GLOBALLY_BANNED
        reasons.append(REJECT_CHARACTER_GLOBALLY_BANNED)
        banned_by = ban_meta.seat
        action_index = ban_meta.log_index
    elif own_pick_meta is not None:
        status = CARD_STATUS_PICKED_BY_SELF
        reasons.append(REJECT_CHARACTER_PICKED_BY_SELF)
        picked_by = own_pick_meta.seat
        action_index = own_pick_meta.log_index
    elif opponent_pick_meta is not None:
        status = CARD_STATUS_BLOCKED_BY_OPPONENT_PICK
        reasons.append(REJECT_CHARACTER_UNAVAILABLE_TO_OPPONENT)
        picked_by = opponent_pick_meta.seat
        action_index = opponent_pick_meta.log_index
    elif is_legal:
        status = CARD_STATUS_LEGAL_TARGET
    else:
        status = CARD_STATUS_AVAILABLE

    if debug:
        for reason in excluded_reasons.get(character_id, ()):
            if reason and reason not in reasons:
                reasons.append(reason)

    return FreeDraftBoardCard(
        character_id=character.character_id,
        display_name=character.display_name,
        element=character.element,
        weapon_type=character.weapon_type,
        rarity=character.rarity,
        level=character.level,
        constellation=character.constellation,
        status=status,
        status_reason_codes=tuple(reasons),
        is_current_legal_target=is_legal,
        is_active_seat_card=(state.current_seat == seat),
        picked_by=picked_by,
        banned_by=banned_by,
        action_index=action_index,
    )


def _global_pools_dict(
    state: DraftSessionState,
    banned_meta_by_id: Mapping[str, _ActionMeta],
) -> dict[str, Any]:
    banned = []
    for character_id in state.banned_character_ids:
        meta = banned_meta_by_id.get(character_id)
        banned.append(
            {
                "character_id": character_id,
                "seat": meta.seat if meta is not None else None,
                "action_index": meta.log_index if meta is not None else None,
                "target_display_name": (
                    meta.target_display_name if meta is not None else ""
                ),
            }
        )
    return {
        "banned": banned,
        "player_1_picked_ids": list(state.player_1_picked_character_ids),
        "player_2_picked_ids": list(state.player_2_picked_character_ids),
        "picked_character_ids_by_seat": {
            SEAT_PLAYER_1: list(state.player_1_picked_character_ids),
            SEAT_PLAYER_2: list(state.player_2_picked_character_ids),
        },
    }


def _timeline(state: DraftSessionState) -> tuple[FreeDraftTimelineStep, ...]:
    rows: list[FreeDraftTimelineStep] = []
    for step_index, step in enumerate(state.schedule.steps):
        actions_total = len(step.actions)
        if state.is_complete or step_index < state.step_index:
            status = TIMELINE_STATUS_COMPLETE
            actions_done = actions_total
        elif step_index == state.step_index:
            status = TIMELINE_STATUS_ACTIVE
            actions_done = min(state.action_index, actions_total)
        else:
            status = TIMELINE_STATUS_PENDING
            actions_done = 0
        rows.append(
            FreeDraftTimelineStep(
                step_index=step_index,
                phase=step.phase,
                seat=step.seat,
                required_actions=tuple(action.action_type for action in step.actions),
                status=status,
                actions_done=actions_done,
                actions_total=actions_total,
            )
        )
    return tuple(rows)


def _summary_dict(controller: "FreeDraftController") -> dict[str, Any]:
    return {
        "assignments": {
            seat: _assignment_summary(controller, seat)
            for seat in PVP_SEATS
        },
        "result": _result_summary(controller),
    }


def _assignment_summary(
    controller: "FreeDraftController",
    seat: str,
) -> dict[str, Any]:
    team_assignment = controller.state.team_assignments.get(seat)
    weapon_assignment = controller.state.weapon_assignments.get(seat)
    team_status = _team_assignment_status(
        controller.session_state,
        team_assignment,
    )
    weapon_status = _weapon_assignment_status(
        controller.session_state,
        team_assignment,
        weapon_assignment,
    )
    return {
        "seat": seat,
        "team_count": (
            len(team_assignment.teams) if team_assignment is not None else 0
        ),
        "team_sizes": (
            [len(team.character_ids) for team in team_assignment.teams]
            if team_assignment is not None
            else []
        ),
        "team_status": team_status["status"],
        "team_issue_codes": team_status["issue_codes"],
        "weapon_assignment_count": (
            len(weapon_assignment.assignments)
            if weapon_assignment is not None
            else 0
        ),
        "weapon_status": weapon_status["status"],
        "weapon_issue_codes": weapon_status["issue_codes"],
    }


def _team_assignment_status(
    state: DraftSessionState,
    assignment: PlayerTeamAssignment | None,
) -> dict[str, Any]:
    if assignment is None:
        return {"status": "not_set", "issue_codes": []}
    validation = validate_team_assignment(state, assignment)
    return {
        "status": validation.status,
        "issue_codes": list(validation.issue_codes()),
    }


def _weapon_assignment_status(
    state: DraftSessionState,
    team_assignment: PlayerTeamAssignment | None,
    weapon_assignment: PlayerWeaponAssignment | None,
) -> dict[str, Any]:
    if weapon_assignment is None:
        return {"status": "not_set", "issue_codes": []}
    if team_assignment is None:
        return {
            "status": "invalid",
            "issue_codes": ["free_draft_controller_assignment_invalid"],
        }
    validation = validate_weapon_assignment(
        state,
        team_assignment,
        weapon_assignment,
    )
    return {
        "status": validation.status,
        "issue_codes": list(validation.issue_codes()),
    }


def _result_summary(controller: "FreeDraftController") -> dict[str, Any] | None:
    result = controller.state.match_result
    if result is None:
        return None
    payload = result.to_dict()
    return {
        "status": payload["status"],
        "winner_seat": payload["winner_seat"],
        "seconds_difference": payload["seconds_difference"],
        "totals": dict(payload["totals"]),
        "technical_loss_count": len(payload["technical_losses"]),
    }


def _action_log_row(meta: _ActionMeta) -> FreeDraftActionLogRow:
    return FreeDraftActionLogRow(
        index=meta.log_index,
        phase=meta.phase,
        seat=meta.seat,
        action_type=meta.action_type,
        target_id=meta.target_id,
        target_display_name=meta.target_display_name,
        accepted=True,
        step_index=meta.step_index,
        action_index=meta.step_action_index,
        sequence=meta.sequence,
    )


def _action_metas(
    state: DraftSessionState,
    decks: Mapping[str, DraftDeck],
) -> tuple[_ActionMeta, ...]:
    positions = _schedule_positions(state)
    rows: list[_ActionMeta] = []
    for log_index, action in enumerate(state.accepted_actions):
        position = positions[log_index] if log_index < len(positions) else None
        rows.append(
            _ActionMeta(
                log_index=log_index,
                phase=position["phase"] if position is not None else "",
                seat=action.seat,
                action_type=action.action_type,
                target_id=action.character_id,
                target_display_name=_display_name_for_action(action, decks),
                step_index=(
                    int(position["step_index"]) if position is not None else None
                ),
                step_action_index=(
                    int(position["action_index"]) if position is not None else None
                ),
                sequence=action.sequence,
            )
        )
    return tuple(rows)


def _schedule_positions(state: DraftSessionState) -> tuple[Mapping[str, Any], ...]:
    positions: list[Mapping[str, Any]] = []
    for step_index, step in enumerate(state.schedule.steps):
        for action_index, requirement in enumerate(step.actions):
            positions.append(
                {
                    "step_index": step_index,
                    "action_index": action_index,
                    "phase": step.phase,
                    "seat": step.seat,
                    "action_type": requirement.action_type,
                }
            )
    return tuple(positions)


def _display_name_for_action(
    action: DraftAction,
    decks: Mapping[str, DraftDeck],
) -> str:
    ordered_seats = (
        (action.seat,) + tuple(seat for seat in PVP_SEATS if seat != action.seat)
        if action.seat in PVP_SEATS
        else PVP_SEATS
    )
    for seat in ordered_seats:
        character = decks[seat].character_by_id.get(action.character_id)
        if character is not None:
            return character.display_name
    return ""


def _excluded_reasons_by_character_id(legal_targets: tuple[Any, ...]) -> dict[str, tuple[str, ...]]:
    reasons: dict[str, list[str]] = {}
    for target in legal_targets:
        if getattr(target, "status", "") != "excluded":
            continue
        character_id = getattr(target, "character_id", "")
        reason = getattr(target, "reason", "")
        if not character_id or not reason:
            continue
        reasons.setdefault(character_id, []).append(reason)
    return {
        character_id: tuple(dict.fromkeys(items))
        for character_id, items in reasons.items()
    }


def _invalid_character_reason_codes(character: DraftCharacter) -> tuple[str, ...]:
    reasons: list[str] = []
    if not character.character_id:
        reasons.append(ISSUE_MISSING_CHARACTER_ID)
    if not character.display_name and not _is_unsupported_traveler(character):
        reasons.append(ISSUE_MISSING_CHARACTER_DISPLAY_NAME)
    if not character.weapon_type:
        reasons.append(ISSUE_MISSING_CHARACTER_WEAPON_TYPE)
    return tuple(reasons)


def _is_unsupported_traveler(character: DraftCharacter) -> bool:
    if character.character_id in UNSUPPORTED_TRAVELER_CHARACTER_IDS:
        return True
    return "traveler" in character.display_name.strip().casefold()


def _assignments_ready(controller: "FreeDraftController") -> bool:
    return (
        set(controller.state.team_assignments) == set(PVP_SEATS)
        and set(controller.state.weapon_assignments) == set(PVP_SEATS)
    )


def _bundle_ready(controller: "FreeDraftController") -> bool:
    return (
        controller.session_state.is_complete
        and _assignments_ready(controller)
        and controller.state.match_result is not None
    )


def _expected_action_total(state: DraftSessionState) -> int:
    return sum(len(step.actions) for step in state.schedule.steps)


def _plain_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key, item in value.items():
        if isinstance(item, Mapping):
            payload[key] = _plain_mapping(item)
        elif isinstance(item, tuple):
            payload[key] = list(item)
        else:
            payload[key] = item
    return payload


def _append_forbidden_token_issues(
    value: Any,
    path: str,
    issues: list[str],
) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            key_text = str(key)
            key_path = f"{path}.{key_text}"
            normalized_key = key_text.strip().casefold()
            for token in FORBIDDEN_BOARD_PROJECTION_TOKENS:
                if token in normalized_key:
                    issues.append(f"forbidden_key:{token}:{key_path}")
            _append_forbidden_token_issues(item, key_path, issues)
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _append_forbidden_token_issues(item, f"{path}[{index}]", issues)
        return
    if isinstance(value, str):
        normalized_value = value.strip().casefold()
        for token in FORBIDDEN_BOARD_PROJECTION_TOKENS:
            if token in normalized_value:
                issues.append(f"forbidden_value:{token}:{path}")


__all__ = [
    "CARD_STATUS_AVAILABLE",
    "CARD_STATUS_BLOCKED_BY_OPPONENT_PICK",
    "CARD_STATUS_GLOBALLY_BANNED",
    "CARD_STATUS_INVALID",
    "CARD_STATUS_LEGAL_TARGET",
    "CARD_STATUS_PICKED_BY_OPPONENT",
    "CARD_STATUS_PICKED_BY_SELF",
    "CARD_STATUS_VALUES",
    "CARD_STATUS_UNAVAILABLE",
    "CARD_STATUS_UNSUPPORTED_TRAVELER",
    "FORBIDDEN_BOARD_PROJECTION_TOKENS",
    "REQUIRED_BOARD_PROJECTION_KEYS",
    "TIMELINE_STATUS_ACTIVE",
    "TIMELINE_STATUS_COMPLETE",
    "TIMELINE_STATUS_PENDING",
    "TIMELINE_STATUS_VALUES",
    "FreeDraftActionLogRow",
    "FreeDraftBoardCard",
    "FreeDraftBoardProjection",
    "FreeDraftBoardSeat",
    "FreeDraftTimelineStep",
    "build_free_draft_board_projection",
    "validate_free_draft_board_projection_dict",
]
