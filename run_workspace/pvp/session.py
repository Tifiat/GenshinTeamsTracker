from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, replace
from typing import Any, Iterable, Mapping

from .deck import DraftDeck
from .schedule import (
    ACTION_BAN_CHARACTER,
    ACTION_PICK_CHARACTER,
    DraftActionRequirement,
    DraftSchedule,
    PVP_SEATS,
    SEAT_PLAYER_1,
    SEAT_PLAYER_2,
    build_default_free_draft_v0_schedule,
    default_free_draft_v0_config,
)
from .validation import (
    SEVERITY_ERROR,
    SimpleValidationReport,
    ValidationIssue,
    validate_draft_deck,
)


REJECT_DRAFT_COMPLETE = "draft_complete"
REJECT_INVALID_SEAT = "invalid_seat"
REJECT_OUT_OF_TURN = "out_of_turn"
REJECT_WRONG_ACTION_TYPE = "wrong_action_type"
REJECT_DUPLICATE_ACTION_ID = "duplicate_action_id"
REJECT_DUPLICATE_SEQUENCE = "duplicate_sequence"
REJECT_MISSING_CHARACTER_ID = "missing_character_id"
REJECT_CHARACTER_ALREADY_BANNED = "character_already_banned"
REJECT_CHARACTER_NOT_IN_ANY_DECK = "character_not_in_any_deck"
REJECT_CHARACTER_NOT_IN_DECK = "character_not_in_deck"
REJECT_CHARACTER_GLOBALLY_BANNED = "character_globally_banned"
REJECT_CHARACTER_PICKED_BY_SELF = "character_picked_by_self"
REJECT_CHARACTER_UNAVAILABLE_TO_OPPONENT = "character_unavailable_to_opponent"

ISSUE_DRAFT_NOT_COMPLETE = "draft_not_complete"
ISSUE_DRAFT_PICK_COUNT_INVALID = "draft_pick_count_invalid"
ISSUE_TEAM_COUNT_INVALID = "team_count_invalid"
ISSUE_DUPLICATE_TEAM_INDEX = "duplicate_team_index"
ISSUE_TEAM_SIZE_INVALID = "team_size_invalid"
ISSUE_MISSING_TEAM_CHARACTER = "missing_team_character"
ISSUE_TEAM_CHARACTER_NOT_PICKED = "team_character_not_picked"
ISSUE_DUPLICATE_TEAM_CHARACTER = "duplicate_team_character"
ISSUE_PICKED_CHARACTER_NOT_ASSIGNED = "picked_character_not_assigned"
ISSUE_TEAM_ASSIGNMENT_INVALID = "team_assignment_invalid"
ISSUE_DUPLICATE_WEAPON_CHARACTER_ASSIGNMENT = "duplicate_weapon_character_assignment"
ISSUE_WEAPON_CHARACTER_NOT_IN_TEAMS = "weapon_character_not_in_teams"
ISSUE_MISSING_WEAPON_STACK_KEY = "missing_weapon_stack_key"
ISSUE_WEAPON_STACK_NOT_IN_DECK = "weapon_stack_not_in_deck"
ISSUE_WEAPON_TYPE_MISMATCH = "weapon_type_mismatch"
ISSUE_WEAPON_ASSIGNMENT_MISSING = "weapon_assignment_missing"
ISSUE_WEAPON_STACK_COUNT_EXCEEDED = "weapon_stack_count_exceeded"


class DraftActionRejected(ValueError):
    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


@dataclass(frozen=True, slots=True)
class DraftAction:
    seat: str
    action_type: str
    character_id: str = ""
    action_id: str = ""
    sequence: int | None = None
    payload: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "sequence": self.sequence,
            "seat": self.seat,
            "type": self.action_type,
            "character_id": self.character_id,
            "payload": dict(sorted(self.payload.items())),
        }


@dataclass(frozen=True, slots=True)
class DraftSessionState:
    player_1_deck: DraftDeck
    player_2_deck: DraftDeck
    schedule: DraftSchedule
    step_index: int = 0
    action_index: int = 0
    banned_character_ids: tuple[str, ...] = ()
    player_1_banned_character_ids: tuple[str, ...] = ()
    player_2_banned_character_ids: tuple[str, ...] = ()
    player_1_picked_character_ids: tuple[str, ...] = ()
    player_2_picked_character_ids: tuple[str, ...] = ()
    accepted_actions: tuple[DraftAction, ...] = ()

    @property
    def is_complete(self) -> bool:
        return self.step_index >= len(self.schedule.steps)

    @property
    def current_requirement(self) -> DraftActionRequirement | None:
        if self.is_complete:
            return None
        step = self.schedule.steps[self.step_index]
        if self.action_index >= len(step.actions):
            return None
        return step.actions[self.action_index]

    @property
    def current_seat(self) -> str | None:
        if self.is_complete:
            return None
        return self.schedule.steps[self.step_index].seat

    def deck_for(self, seat: str) -> DraftDeck:
        if seat == SEAT_PLAYER_1:
            return self.player_1_deck
        if seat == SEAT_PLAYER_2:
            return self.player_2_deck
        raise DraftActionRejected(REJECT_INVALID_SEAT)

    def opponent_seat(self, seat: str) -> str:
        if seat == SEAT_PLAYER_1:
            return SEAT_PLAYER_2
        if seat == SEAT_PLAYER_2:
            return SEAT_PLAYER_1
        raise DraftActionRejected(REJECT_INVALID_SEAT)

    def picked_character_ids_for(self, seat: str) -> tuple[str, ...]:
        if seat == SEAT_PLAYER_1:
            return self.player_1_picked_character_ids
        if seat == SEAT_PLAYER_2:
            return self.player_2_picked_character_ids
        raise DraftActionRejected(REJECT_INVALID_SEAT)

    def banned_character_ids_for(self, seat: str) -> tuple[str, ...]:
        if seat == SEAT_PLAYER_1:
            return self.player_1_banned_character_ids
        if seat == SEAT_PLAYER_2:
            return self.player_2_banned_character_ids
        raise DraftActionRejected(REJECT_INVALID_SEAT)

    def state_hash(self) -> str:
        payload = json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "player_1_deck": self.player_1_deck.to_dict(),
            "player_2_deck": self.player_2_deck.to_dict(),
            "schedule": self.schedule.to_dict(),
            "step_index": self.step_index,
            "action_index": self.action_index,
            "is_complete": self.is_complete,
            "current_seat": self.current_seat,
            "current_requirement": (
                self.current_requirement.to_dict()
                if self.current_requirement is not None
                else None
            ),
            "banned_character_ids": list(self.banned_character_ids),
            "banned_character_ids_by_seat": {
                SEAT_PLAYER_1: list(self.player_1_banned_character_ids),
                SEAT_PLAYER_2: list(self.player_2_banned_character_ids),
            },
            "picked_character_ids_by_seat": {
                SEAT_PLAYER_1: list(self.player_1_picked_character_ids),
                SEAT_PLAYER_2: list(self.player_2_picked_character_ids),
            },
            "accepted_actions": [item.to_dict() for item in self.accepted_actions],
        }


@dataclass(frozen=True, slots=True)
class TeamAssignment:
    team_index: int
    character_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "team_index": self.team_index,
            "character_ids": list(self.character_ids),
        }


@dataclass(frozen=True, slots=True)
class PlayerTeamAssignment:
    seat: str
    teams: tuple[TeamAssignment, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "seat": self.seat,
            "teams": [item.to_dict() for item in self.teams],
        }


@dataclass(frozen=True, slots=True)
class CharacterWeaponAssignment:
    character_id: str
    weapon_stack_key: str

    def to_dict(self) -> dict[str, str]:
        return {
            "character_id": self.character_id,
            "weapon_stack_key": self.weapon_stack_key,
        }


@dataclass(frozen=True, slots=True)
class PlayerWeaponAssignment:
    seat: str
    assignments: tuple[CharacterWeaponAssignment, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "seat": self.seat,
            "assignments": [item.to_dict() for item in self.assignments],
        }


def create_draft_session(
    player_1_deck: DraftDeck,
    player_2_deck: DraftDeck,
    *,
    schedule: DraftSchedule | None = None,
    validate_decks: bool = True,
) -> DraftSessionState:
    if validate_decks:
        player_1_report = validate_draft_deck(player_1_deck)
        player_2_report = validate_draft_deck(player_2_deck)
        if not player_1_report.ready or not player_2_report.ready:
            raise ValueError(
                "Draft session requires validated decks without validation errors."
            )
    return DraftSessionState(
        player_1_deck=player_1_deck,
        player_2_deck=player_2_deck,
        schedule=schedule or build_default_free_draft_v0_schedule(),
    )


def apply_draft_action(
    state: DraftSessionState,
    action: DraftAction,
) -> DraftSessionState:
    requirement = state.current_requirement
    if requirement is None:
        raise DraftActionRejected(REJECT_DRAFT_COMPLETE)
    if action.seat not in PVP_SEATS:
        raise DraftActionRejected(REJECT_INVALID_SEAT)
    if action.seat != state.current_seat:
        raise DraftActionRejected(REJECT_OUT_OF_TURN)
    if action.action_type != requirement.action_type:
        raise DraftActionRejected(REJECT_WRONG_ACTION_TYPE)
    if action.action_id and action.action_id in {
        item.action_id for item in state.accepted_actions if item.action_id
    }:
        raise DraftActionRejected(REJECT_DUPLICATE_ACTION_ID)
    if action.sequence is not None and action.sequence in {
        item.sequence for item in state.accepted_actions if item.sequence is not None
    }:
        raise DraftActionRejected(REJECT_DUPLICATE_SEQUENCE)

    character_id = action.character_id.strip()
    if not character_id:
        raise DraftActionRejected(REJECT_MISSING_CHARACTER_ID)

    if action.action_type == ACTION_BAN_CHARACTER:
        state = _apply_ban(state, action, character_id)
    elif action.action_type == ACTION_PICK_CHARACTER:
        state = _apply_pick(state, action, character_id)
    else:
        raise DraftActionRejected(REJECT_WRONG_ACTION_TYPE)

    return _advance_after_accepting(state, action)


def replay_draft_actions(
    initial_state: DraftSessionState,
    actions: Iterable[DraftAction],
) -> DraftSessionState:
    state = initial_state
    for action in actions:
        state = apply_draft_action(state, action)
    return state


def validate_team_assignment(
    state: DraftSessionState,
    assignment: PlayerTeamAssignment,
) -> SimpleValidationReport:
    config = default_free_draft_v0_config()
    issues: list[ValidationIssue] = []
    if assignment.seat not in PVP_SEATS:
        issues.append(_issue(ISSUE_TEAM_ASSIGNMENT_INVALID, path="seat"))
        return SimpleValidationReport(tuple(issues))

    picks = state.picked_character_ids_for(assignment.seat)
    pick_set = set(picks)
    if not state.is_complete:
        issues.append(_issue(ISSUE_DRAFT_NOT_COMPLETE))
    if len(picks) != config.picks_per_player:
        issues.append(
            _issue(
                ISSUE_DRAFT_PICK_COUNT_INVALID,
                details={
                    "expected": config.picks_per_player,
                    "actual": len(picks),
                },
            )
        )
    if len(assignment.teams) != config.teams_per_player:
        issues.append(
            _issue(
                ISSUE_TEAM_COUNT_INVALID,
                path="teams",
                details={
                    "expected": config.teams_per_player,
                    "actual": len(assignment.teams),
                },
            )
        )

    assigned: list[str] = []
    seen_team_indexes: set[int] = set()
    for team_position, team in enumerate(assignment.teams):
        team_path = f"teams[{team_position}]"
        if team.team_index in seen_team_indexes:
            issues.append(
                _issue(
                    ISSUE_DUPLICATE_TEAM_INDEX,
                    path=f"{team_path}.team_index",
                    details={"team_index": team.team_index},
                )
            )
        seen_team_indexes.add(team.team_index)
        if len(team.character_ids) != config.team_size:
            issues.append(
                _issue(
                    ISSUE_TEAM_SIZE_INVALID,
                    path=f"{team_path}.character_ids",
                    details={
                        "expected": config.team_size,
                        "actual": len(team.character_ids),
                    },
                )
            )
        for slot_index, character_id in enumerate(team.character_ids):
            character_path = f"{team_path}.character_ids[{slot_index}]"
            if not character_id:
                issues.append(_issue(ISSUE_MISSING_TEAM_CHARACTER, path=character_path))
                continue
            if character_id not in pick_set:
                issues.append(
                    _issue(
                        ISSUE_TEAM_CHARACTER_NOT_PICKED,
                        path=character_path,
                        details={"character_id": character_id},
                    )
                )
            if character_id in assigned:
                issues.append(
                    _issue(
                        ISSUE_DUPLICATE_TEAM_CHARACTER,
                        path=character_path,
                        details={"character_id": character_id},
                    )
                )
            assigned.append(character_id)

    assigned_set = set(assigned)
    for character_id in picks:
        if character_id not in assigned_set:
            issues.append(
                _issue(
                    ISSUE_PICKED_CHARACTER_NOT_ASSIGNED,
                    path="teams",
                    details={"character_id": character_id},
                )
            )

    return SimpleValidationReport(issues=tuple(issues))


def validate_weapon_assignment(
    state: DraftSessionState,
    team_assignment: PlayerTeamAssignment,
    weapon_assignment: PlayerWeaponAssignment,
) -> SimpleValidationReport:
    issues: list[ValidationIssue] = []
    if weapon_assignment.seat != team_assignment.seat:
        issues.append(_issue(ISSUE_TEAM_ASSIGNMENT_INVALID, path="seat"))
        return SimpleValidationReport(tuple(issues))

    team_report = validate_team_assignment(state, team_assignment)
    if not team_report.ready:
        issues.append(
            _issue(
                ISSUE_TEAM_ASSIGNMENT_INVALID,
                details={"issue_codes": list(team_report.issue_codes())},
            )
        )

    deck = state.deck_for(weapon_assignment.seat)
    character_by_id = deck.character_by_id
    stack_by_key = deck.weapon_stack_by_key
    team_character_ids = tuple(
        character_id
        for team in team_assignment.teams
        for character_id in team.character_ids
        if character_id
    )
    team_character_set = set(team_character_ids)

    assigned_characters: set[str] = set()
    stack_usage: dict[str, int] = {}
    for index, assignment in enumerate(weapon_assignment.assignments):
        path = f"assignments[{index}]"
        character_id = assignment.character_id
        stack_key = assignment.weapon_stack_key
        if character_id in assigned_characters:
            issues.append(
                _issue(
                    ISSUE_DUPLICATE_WEAPON_CHARACTER_ASSIGNMENT,
                    path=f"{path}.character_id",
                    details={"character_id": character_id},
                )
            )
        assigned_characters.add(character_id)
        if character_id not in team_character_set:
            issues.append(
                _issue(
                    ISSUE_WEAPON_CHARACTER_NOT_IN_TEAMS,
                    path=f"{path}.character_id",
                    details={"character_id": character_id},
                )
            )
        if not stack_key:
            issues.append(_issue(ISSUE_MISSING_WEAPON_STACK_KEY, path=f"{path}.weapon_stack_key"))
            continue
        stack = stack_by_key.get(stack_key)
        if stack is None:
            issues.append(
                _issue(
                    ISSUE_WEAPON_STACK_NOT_IN_DECK,
                    path=f"{path}.weapon_stack_key",
                    details={"weapon_stack_key": stack_key},
                )
            )
            continue
        character = character_by_id.get(character_id)
        if character is not None and _norm(character.weapon_type) != _norm(stack.weapon_type):
            issues.append(
                _issue(
                    ISSUE_WEAPON_TYPE_MISMATCH,
                    path=path,
                    details={
                        "character_id": character_id,
                        "character_weapon_type": character.weapon_type,
                        "weapon_stack_key": stack_key,
                        "weapon_type": stack.weapon_type,
                    },
                )
            )
        stack_usage[stack_key] = stack_usage.get(stack_key, 0) + 1

    for character_id in team_character_ids:
        if character_id not in assigned_characters:
            issues.append(
                _issue(
                    ISSUE_WEAPON_ASSIGNMENT_MISSING,
                    path="assignments",
                    details={"character_id": character_id},
                )
            )

    for stack_key, used_count in sorted(stack_usage.items()):
        stack = stack_by_key.get(stack_key)
        available_count = stack.count if stack is not None and stack.count is not None else 0
        if used_count > available_count:
            issues.append(
                _issue(
                    ISSUE_WEAPON_STACK_COUNT_EXCEEDED,
                    path="assignments",
                    details={
                        "weapon_stack_key": stack_key,
                        "available_count": available_count,
                        "used_count": used_count,
                    },
                )
            )

    return SimpleValidationReport(issues=tuple(issues))


def _apply_ban(
    state: DraftSessionState,
    action: DraftAction,
    character_id: str,
) -> DraftSessionState:
    if character_id in state.banned_character_ids:
        raise DraftActionRejected(REJECT_CHARACTER_ALREADY_BANNED)
    if (
        character_id not in state.player_1_deck.character_ids
        and character_id not in state.player_2_deck.character_ids
    ):
        raise DraftActionRejected(REJECT_CHARACTER_NOT_IN_ANY_DECK)

    if action.seat == SEAT_PLAYER_1:
        return replace(
            state,
            banned_character_ids=state.banned_character_ids + (character_id,),
            player_1_banned_character_ids=(
                state.player_1_banned_character_ids + (character_id,)
            ),
        )
    return replace(
        state,
        banned_character_ids=state.banned_character_ids + (character_id,),
        player_2_banned_character_ids=(
            state.player_2_banned_character_ids + (character_id,)
        ),
    )


def _apply_pick(
    state: DraftSessionState,
    action: DraftAction,
    character_id: str,
) -> DraftSessionState:
    seat_deck = state.deck_for(action.seat)
    own_picks = state.picked_character_ids_for(action.seat)
    opponent_picks = state.picked_character_ids_for(state.opponent_seat(action.seat))

    if character_id not in seat_deck.character_ids:
        raise DraftActionRejected(REJECT_CHARACTER_NOT_IN_DECK)
    if character_id in state.banned_character_ids:
        raise DraftActionRejected(REJECT_CHARACTER_GLOBALLY_BANNED)
    if character_id in own_picks:
        raise DraftActionRejected(REJECT_CHARACTER_PICKED_BY_SELF)
    if character_id in opponent_picks:
        raise DraftActionRejected(REJECT_CHARACTER_UNAVAILABLE_TO_OPPONENT)

    if action.seat == SEAT_PLAYER_1:
        return replace(
            state,
            player_1_picked_character_ids=own_picks + (character_id,),
        )
    return replace(
        state,
        player_2_picked_character_ids=own_picks + (character_id,),
    )


def _advance_after_accepting(
    state: DraftSessionState,
    action: DraftAction,
) -> DraftSessionState:
    step = state.schedule.steps[state.step_index]
    next_step_index = state.step_index
    next_action_index = state.action_index + 1
    if next_action_index >= len(step.actions):
        next_step_index += 1
        next_action_index = 0
    return replace(
        state,
        step_index=next_step_index,
        action_index=next_action_index,
        accepted_actions=state.accepted_actions + (action,),
    )


def _issue(
    code: str,
    *,
    path: str = "",
    details: Mapping[str, Any] | None = None,
) -> ValidationIssue:
    return ValidationIssue(
        code=code,
        severity=SEVERITY_ERROR,
        path=path,
        details=details or {},
    )


def _norm(value: str) -> str:
    return value.strip().casefold()
