"""Deterministic Free Draft v0 smoke planner.

This module is a backend test/dev harness, not a gameplay optimizer. It chooses
the first reducer-accepted character action from stable local deck order, then
builds simple post-draft teams and weapon assignments for smoke coverage.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .deck import DraftCharacter, DraftDeck, DraftWeaponStack
from .draft_system import (
    DRAFT_SYSTEM_FREE_DRAFT_V0,
    DraftSystemDefinition,
    require_draft_system,
)
from .schedule import (
    ACTION_BAN_CHARACTER,
    ACTION_PICK_CHARACTER,
    PVP_SEATS,
    DraftSchedule,
    SEAT_PLAYER_1,
    SEAT_PLAYER_2,
    default_free_draft_v0_config,
)
from .session import (
    CharacterWeaponAssignment,
    DraftAction,
    DraftActionRejected,
    DraftSessionState,
    PlayerTeamAssignment,
    PlayerWeaponAssignment,
    TeamAssignment,
    apply_draft_action,
    create_draft_session,
    validate_team_assignment,
    validate_weapon_assignment,
)
from .validation import SEVERITY_ERROR, SimpleValidationReport


ISSUE_DRAFT_SESSION_CREATE_FAILED = "draft_session_create_failed"
ISSUE_UNSUPPORTED_DRAFT_ACTION = "unsupported_draft_action"
ISSUE_NO_LEGAL_DRAFT_ACTION = "no_legal_draft_action"
ISSUE_TEAM_ASSIGNMENT_PICK_COUNT_INVALID = "team_assignment_pick_count_invalid"
ISSUE_TEAM_ASSIGNMENT_INVALID = "team_assignment_invalid"
ISSUE_WEAPON_CHARACTER_NOT_IN_DECK = "weapon_character_not_in_deck"
ISSUE_NO_COMPATIBLE_WEAPON_STACK = "no_compatible_weapon_stack"
ISSUE_WEAPON_ASSIGNMENT_INVALID = "weapon_assignment_invalid"


@dataclass(frozen=True, slots=True)
class FreeDraftPlannerIssue:
    code: str
    severity: str
    message: str = ""
    step_index: int | None = None
    action_index: int | None = None
    seat: str = ""
    action_type: str = ""
    details: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "step_index": self.step_index,
            "action_index": self.action_index,
            "seat": self.seat,
            "action_type": self.action_type,
            "details": dict(sorted(self.details.items())),
        }


@dataclass(frozen=True, slots=True)
class FreeDraftActionPlanReport:
    initial_state: DraftSessionState | None
    final_state: DraftSessionState | None
    actions: tuple[DraftAction, ...] = ()
    issues: tuple[FreeDraftPlannerIssue, ...] = ()

    @property
    def ready(self) -> bool:
        return (
            self.final_state is not None
            and self.final_state.is_complete
            and not _has_error_issues(self.issues)
        )

    @property
    def action_count(self) -> int:
        return len(self.actions)

    @property
    def schedule_steps_count(self) -> int:
        state = self.final_state or self.initial_state
        return len(state.schedule.steps) if state is not None else 0

    def issue_codes(self) -> tuple[str, ...]:
        return tuple(issue.code for issue in self.issues)

    def to_dict(self) -> dict[str, Any]:
        final = self.final_state
        return {
            "ready": self.ready,
            "schedule_steps_count": self.schedule_steps_count,
            "action_count": self.action_count,
            "initial_state_hash": (
                self.initial_state.state_hash() if self.initial_state is not None else ""
            ),
            "final_state_hash": final.state_hash() if final is not None else "",
            "is_complete": final.is_complete if final is not None else False,
            "banned_character_ids_by_seat": (
                {
                    SEAT_PLAYER_1: list(final.player_1_banned_character_ids),
                    SEAT_PLAYER_2: list(final.player_2_banned_character_ids),
                }
                if final is not None
                else {}
            ),
            "picked_character_ids_by_seat": (
                {
                    SEAT_PLAYER_1: list(final.player_1_picked_character_ids),
                    SEAT_PLAYER_2: list(final.player_2_picked_character_ids),
                }
                if final is not None
                else {}
            ),
            "actions": [action.to_dict() for action in self.actions],
            "issues": [issue.to_dict() for issue in self.issues],
        }


@dataclass(frozen=True, slots=True)
class FreeDraftTeamPlanReport:
    seat: str
    assignment: PlayerTeamAssignment
    validation_report: SimpleValidationReport
    issues: tuple[FreeDraftPlannerIssue, ...] = ()

    @property
    def ready(self) -> bool:
        return self.validation_report.ready and not _has_error_issues(self.issues)

    def issue_codes(self) -> tuple[str, ...]:
        return tuple(issue.code for issue in self.issues)

    def to_dict(self) -> dict[str, Any]:
        return {
            "seat": self.seat,
            "ready": self.ready,
            "assignment": self.assignment.to_dict(),
            "validation_report": self.validation_report.to_dict(),
            "issues": [issue.to_dict() for issue in self.issues],
        }


@dataclass(frozen=True, slots=True)
class FreeDraftWeaponPlanReport:
    seat: str
    assignment: PlayerWeaponAssignment
    validation_report: SimpleValidationReport
    stack_usage: Mapping[str, int] = field(default_factory=dict)
    issues: tuple[FreeDraftPlannerIssue, ...] = ()

    @property
    def ready(self) -> bool:
        return self.validation_report.ready and not _has_error_issues(self.issues)

    def issue_codes(self) -> tuple[str, ...]:
        return tuple(issue.code for issue in self.issues)

    def to_dict(self) -> dict[str, Any]:
        return {
            "seat": self.seat,
            "ready": self.ready,
            "assignment": self.assignment.to_dict(),
            "validation_report": self.validation_report.to_dict(),
            "stack_usage": dict(sorted(self.stack_usage.items())),
            "issues": [issue.to_dict() for issue in self.issues],
        }


def plan_free_draft_actions(
    player_1_deck: DraftDeck,
    player_2_deck: DraftDeck,
    *,
    schedule: DraftSchedule | None = None,
    draft_system: DraftSystemDefinition | None = None,
    system_id: str = DRAFT_SYSTEM_FREE_DRAFT_V0,
) -> FreeDraftActionPlanReport:
    """Autoplay the current Free Draft schedule through reducer-accepted actions."""

    try:
        if schedule is None:
            schedule = (draft_system or require_draft_system(system_id)).build_schedule()
        initial_state = create_draft_session(
            player_1_deck,
            player_2_deck,
            schedule=schedule,
        )
    except Exception as exc:
        return FreeDraftActionPlanReport(
            initial_state=None,
            final_state=None,
            issues=(
                _issue(
                    ISSUE_DRAFT_SESSION_CREATE_FAILED,
                    message=str(exc),
                ),
            ),
        )

    state = initial_state
    issues: list[FreeDraftPlannerIssue] = []
    sequence = 1

    while not state.is_complete:
        requirement = state.current_requirement
        seat = state.current_seat or ""
        if requirement is None or seat not in PVP_SEATS:
            issues.append(
                _issue(
                    ISSUE_NO_LEGAL_DRAFT_ACTION,
                    step_index=state.step_index,
                    action_index=state.action_index,
                    seat=seat,
                    message="The draft schedule has no actionable current requirement.",
                )
            )
            break
        if requirement.action_type not in {ACTION_BAN_CHARACTER, ACTION_PICK_CHARACTER}:
            issues.append(
                _issue(
                    ISSUE_UNSUPPORTED_DRAFT_ACTION,
                    step_index=state.step_index,
                    action_index=state.action_index,
                    seat=seat,
                    action_type=requirement.action_type,
                    message="The smoke planner only supports character bans and picks.",
                )
            )
            break

        rejections: list[dict[str, str]] = []
        accepted = False
        for character_id in _candidate_character_ids(
            state,
            seat,
            requirement.action_type,
        ):
            action = DraftAction(
                seat=seat,
                action_type=requirement.action_type,
                character_id=character_id,
                action_id=f"free-draft-planner-{sequence}",
                sequence=sequence,
            )
            try:
                state = apply_draft_action(state, action)
            except DraftActionRejected as exc:
                rejections.append({"character_id": character_id, "code": exc.code})
                continue
            sequence += 1
            accepted = True
            break

        if not accepted:
            issues.append(
                _issue(
                    ISSUE_NO_LEGAL_DRAFT_ACTION,
                    step_index=state.step_index,
                    action_index=state.action_index,
                    seat=seat,
                    action_type=requirement.action_type,
                    message="No deterministic candidate was accepted by the reducer.",
                    details={"rejections": rejections},
                )
            )
            break

    return FreeDraftActionPlanReport(
        initial_state=initial_state,
        final_state=state,
        actions=state.accepted_actions,
        issues=tuple(issues),
    )


def plan_free_draft_team_assignment(
    state: DraftSessionState,
    seat: str,
) -> FreeDraftTeamPlanReport:
    config = default_free_draft_v0_config()
    picks = state.picked_character_ids_for(seat)
    assignment = PlayerTeamAssignment(
        seat=seat,
        teams=(
            TeamAssignment(team_index=0, character_ids=picks[: config.team_size]),
            TeamAssignment(
                team_index=1,
                character_ids=picks[config.team_size : config.picks_per_player],
            ),
        ),
    )
    validation = validate_team_assignment(state, assignment)
    issues: list[FreeDraftPlannerIssue] = []
    if len(picks) != config.picks_per_player:
        issues.append(
            _issue(
                ISSUE_TEAM_ASSIGNMENT_PICK_COUNT_INVALID,
                seat=seat,
                message="Free Draft team assignment requires exactly 8 picks.",
                details={"expected": config.picks_per_player, "actual": len(picks)},
            )
        )
    if not validation.ready:
        issues.append(
            _issue(
                ISSUE_TEAM_ASSIGNMENT_INVALID,
                seat=seat,
                message="Generated team assignment failed validation.",
                details={"issue_codes": list(validation.issue_codes())},
            )
        )
    return FreeDraftTeamPlanReport(
        seat=seat,
        assignment=assignment,
        validation_report=validation,
        issues=tuple(issues),
    )


def plan_free_draft_weapon_assignment(
    state: DraftSessionState,
    team_assignment: PlayerTeamAssignment,
) -> FreeDraftWeaponPlanReport:
    seat = team_assignment.seat
    deck = state.deck_for(seat)
    assignments: list[CharacterWeaponAssignment] = []
    issues: list[FreeDraftPlannerIssue] = []
    stack_usage: dict[str, int] = {}

    for character_id in _team_character_ids(team_assignment):
        character = deck.character_by_id.get(character_id)
        if character is None:
            issues.append(
                _issue(
                    ISSUE_WEAPON_CHARACTER_NOT_IN_DECK,
                    seat=seat,
                    message="Team character is not present in the player's deck.",
                    details={"character_id": character_id},
                )
            )
            continue

        stack = _first_available_compatible_stack(deck, character, stack_usage)
        if stack is None:
            issues.append(
                _issue(
                    ISSUE_NO_COMPATIBLE_WEAPON_STACK,
                    seat=seat,
                    message="No compatible weapon stack remained for this character.",
                    details={
                        "character_id": character_id,
                        "weapon_type": character.weapon_type,
                    },
                )
            )
            continue

        stack_usage[stack.stack_key] = stack_usage.get(stack.stack_key, 0) + 1
        assignments.append(
            CharacterWeaponAssignment(
                character_id=character_id,
                weapon_stack_key=stack.stack_key,
            )
        )

    assignment = PlayerWeaponAssignment(seat=seat, assignments=tuple(assignments))
    validation = validate_weapon_assignment(state, team_assignment, assignment)
    if not validation.ready:
        issues.append(
            _issue(
                ISSUE_WEAPON_ASSIGNMENT_INVALID,
                seat=seat,
                message="Generated weapon assignment failed validation.",
                details={"issue_codes": list(validation.issue_codes())},
            )
        )

    return FreeDraftWeaponPlanReport(
        seat=seat,
        assignment=assignment,
        validation_report=validation,
        stack_usage=stack_usage,
        issues=tuple(issues),
    )


def _candidate_character_ids(
    state: DraftSessionState,
    seat: str,
    action_type: str,
) -> tuple[str, ...]:
    if action_type == ACTION_PICK_CHARACTER:
        return _pick_candidate_ids(state, seat)
    if action_type == ACTION_BAN_CHARACTER:
        return _ban_candidate_ids(state, seat)
    return ()


def _pick_candidate_ids(state: DraftSessionState, seat: str) -> tuple[str, ...]:
    blocked = set(state.banned_character_ids)
    blocked.update(state.player_1_picked_character_ids)
    blocked.update(state.player_2_picked_character_ids)
    return tuple(
        character.character_id
        for character in sorted(state.deck_for(seat).characters, key=_character_sort_key)
        if character.character_id and character.character_id not in blocked
    )


def _ban_candidate_ids(state: DraftSessionState, seat: str) -> tuple[str, ...]:
    blocked = set(state.banned_character_ids)
    blocked.update(state.player_1_picked_character_ids)
    blocked.update(state.player_2_picked_character_ids)
    candidates: list[str] = []
    seen: set[str] = set()

    for deck in (state.deck_for(state.opponent_seat(seat)), state.deck_for(seat)):
        for character in sorted(deck.characters, key=_character_sort_key):
            character_id = character.character_id
            if not character_id or character_id in blocked or character_id in seen:
                continue
            seen.add(character_id)
            candidates.append(character_id)

    return tuple(candidates)


def _team_character_ids(assignment: PlayerTeamAssignment) -> tuple[str, ...]:
    return tuple(
        character_id
        for team in assignment.teams
        for character_id in team.character_ids
        if character_id
    )


def _first_available_compatible_stack(
    deck: DraftDeck,
    character: DraftCharacter,
    stack_usage: Mapping[str, int],
) -> DraftWeaponStack | None:
    weapon_type = _norm(character.weapon_type)
    for stack in sorted(deck.weapons, key=_weapon_stack_sort_key):
        if _norm(stack.weapon_type) != weapon_type:
            continue
        available_count = stack.count if stack.count is not None else 0
        if stack_usage.get(stack.stack_key, 0) < available_count:
            return stack
    return None


def _character_sort_key(character: DraftCharacter) -> tuple[str, str]:
    return (character.character_id.strip(), character.display_name.casefold())


def _weapon_stack_sort_key(stack: DraftWeaponStack) -> tuple[str, str, int, int, int, str, str]:
    return (
        _norm(stack.weapon_type),
        stack.weapon_id.strip(),
        stack.rarity or 0,
        stack.level or 0,
        stack.refinement or 0,
        stack.display_name.casefold(),
        stack.stack_key,
    )


def _issue(
    code: str,
    *,
    message: str = "",
    step_index: int | None = None,
    action_index: int | None = None,
    seat: str = "",
    action_type: str = "",
    details: Mapping[str, Any] | None = None,
) -> FreeDraftPlannerIssue:
    return FreeDraftPlannerIssue(
        code=code,
        severity=SEVERITY_ERROR,
        message=message,
        step_index=step_index,
        action_index=action_index,
        seat=seat,
        action_type=action_type,
        details=details or {},
    )


def _has_error_issues(issues: tuple[FreeDraftPlannerIssue, ...]) -> bool:
    return any(issue.severity == SEVERITY_ERROR for issue in issues)


def _norm(value: str) -> str:
    return value.strip().casefold()
