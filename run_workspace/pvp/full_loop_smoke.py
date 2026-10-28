"""Developer smoke for the PvP v0 backend using synthetic sample decks.

This module intentionally scripts fixture-only character ids, team splits,
weapon choices, and timers from `samples/pvp/`. Future UI/deck-builder work
should provide real user-selected decks/actions instead of extending this as
product logic; tests pin it as a deterministic backend integration harness.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .deck import DraftDeck, load_draft_deck
from .draft_system import DRAFT_SYSTEM_FREE_DRAFT_V0, require_draft_system
from .match_result import (
    ChamberTimer,
    MatchResult,
    PlayerMatchTimers,
    calculate_match_result,
)
from .schedule import (
    ACTION_BAN_CHARACTER,
    ACTION_PICK_CHARACTER,
    SEAT_PLAYER_1,
    SEAT_PLAYER_2,
)
from .session import (
    CharacterWeaponAssignment,
    DraftAction,
    DraftSessionState,
    PlayerTeamAssignment,
    PlayerWeaponAssignment,
    TeamAssignment,
    apply_draft_action,
    create_draft_session,
    replay_draft_actions,
    validate_team_assignment,
    validate_weapon_assignment,
)
from .validation import DeckValidationReport, validate_draft_deck


PVP_PACKAGE_DIR = Path(__file__).resolve().parent
REPO_ROOT = PVP_PACKAGE_DIR.parents[1]
DEFAULT_SAMPLE_DIR = REPO_ROOT / "samples" / "pvp"
DEFAULT_PLAYER_1_DECK_PATH = DEFAULT_SAMPLE_DIR / "free_draft_player_1_deck.json"
DEFAULT_PLAYER_2_DECK_PATH = DEFAULT_SAMPLE_DIR / "free_draft_player_2_deck.json"


class PvpFullLoopSmokeError(RuntimeError):
    """Raised when the deterministic backend smoke scenario cannot complete."""


@dataclass(frozen=True, slots=True)
class PvpSeatSmokeSummary:
    seat: str
    nickname: str
    deck_name: str
    deck_path: str
    validation_status: str
    banned_character_ids: tuple[str, ...]
    picked_character_ids: tuple[str, ...]
    teams: PlayerTeamAssignment
    weapons: PlayerWeaponAssignment
    timer_total_seconds: int
    weapon_stack_usage: Mapping[str, int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "seat": self.seat,
            "nickname": self.nickname,
            "deck_name": self.deck_name,
            "deck_path": self.deck_path,
            "validation_status": self.validation_status,
            "banned_character_ids": list(self.banned_character_ids),
            "picked_character_ids": list(self.picked_character_ids),
            "teams": self.teams.to_dict(),
            "weapons": self.weapons.to_dict(),
            "timer_total_seconds": self.timer_total_seconds,
            "weapon_stack_usage": dict(sorted(self.weapon_stack_usage.items())),
        }


@dataclass(frozen=True, slots=True)
class PvpFullLoopSmokeReport:
    scenario_name: str
    schedule_steps_count: int
    action_count: int
    accepted_actions: tuple[DraftAction, ...]
    state_hash: str
    replay_state_hash: str
    player_1: PvpSeatSmokeSummary
    player_2: PvpSeatSmokeSummary
    match_result: MatchResult

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_name": self.scenario_name,
            "schedule_steps_count": self.schedule_steps_count,
            "action_count": self.action_count,
            "accepted_actions": [item.to_dict() for item in self.accepted_actions],
            "state_hash": self.state_hash,
            "replay_state_hash": self.replay_state_hash,
            "player_1": self.player_1.to_dict(),
            "player_2": self.player_2.to_dict(),
            "match_result": self.match_result.to_dict(),
        }


def run_default_full_loop_smoke(
    *,
    player_1_deck_path: str | Path = DEFAULT_PLAYER_1_DECK_PATH,
    player_2_deck_path: str | Path = DEFAULT_PLAYER_2_DECK_PATH,
) -> PvpFullLoopSmokeReport:
    player_1_path = Path(player_1_deck_path)
    player_2_path = Path(player_2_deck_path)
    player_1_deck = load_draft_deck(player_1_path)
    player_2_deck = load_draft_deck(player_2_path)

    player_1_validation = validate_draft_deck(player_1_deck)
    player_2_validation = validate_draft_deck(player_2_deck)
    _require_ready_deck(SEAT_PLAYER_1, player_1_validation)
    _require_ready_deck(SEAT_PLAYER_2, player_2_validation)

    draft_system = require_draft_system(DRAFT_SYSTEM_FREE_DRAFT_V0)
    schedule = draft_system.build_schedule()
    initial_state = create_draft_session(
        player_1_deck,
        player_2_deck,
        schedule=schedule,
    )
    state = initial_state
    actions = default_full_loop_actions()
    for action in actions:
        state = apply_draft_action(state, action)

    replayed = replay_draft_actions(initial_state, state.accepted_actions)
    if replayed.to_dict() != state.to_dict():
        raise PvpFullLoopSmokeError("Draft replay diverged from final state.")
    if replayed.state_hash() != state.state_hash():
        raise PvpFullLoopSmokeError("Draft replay hash diverged from final state.")
    _require_complete_pick_counts(state)

    player_1_teams = _team_assignment(
        SEAT_PLAYER_1,
        state.player_1_picked_character_ids,
    )
    player_2_teams = _team_assignment(
        SEAT_PLAYER_2,
        state.player_2_picked_character_ids,
    )
    _require_ready_report(
        "player_1 team assignment",
        validate_team_assignment(state, player_1_teams),
    )
    _require_ready_report(
        "player_2 team assignment",
        validate_team_assignment(state, player_2_teams),
    )

    player_1_weapons = _weapon_assignment_for(state, player_1_teams)
    player_2_weapons = _weapon_assignment_for(state, player_2_teams)
    _require_ready_report(
        "player_1 weapon assignment",
        validate_weapon_assignment(state, player_1_teams, player_1_weapons),
    )
    _require_ready_report(
        "player_2 weapon assignment",
        validate_weapon_assignment(state, player_2_teams, player_2_weapons),
    )

    player_1_timers = PlayerMatchTimers(
        seat=SEAT_PLAYER_1,
        chambers=(
            ChamberTimer("abyss-12", "chamber-1", 90),
            ChamberTimer("abyss-12", "chamber-2", 105),
            ChamberTimer("abyss-12", "chamber-3", 120),
        ),
    )
    player_2_timers = PlayerMatchTimers(
        seat=SEAT_PLAYER_2,
        chambers=(
            ChamberTimer("abyss-12", "chamber-1", 100),
            ChamberTimer("abyss-12", "chamber-2", 115),
            ChamberTimer("abyss-12", "chamber-3", 130),
        ),
    )
    result = calculate_match_result(player_1_timers, player_2_timers)

    return PvpFullLoopSmokeReport(
        scenario_name="free_draft_v0_fixture_full_loop",
        schedule_steps_count=len(schedule.steps),
        action_count=len(state.accepted_actions),
        accepted_actions=state.accepted_actions,
        state_hash=state.state_hash(),
        replay_state_hash=replayed.state_hash(),
        player_1=_seat_summary(
            seat=SEAT_PLAYER_1,
            deck=player_1_deck,
            deck_path=player_1_path,
            validation=player_1_validation,
            state=state,
            teams=player_1_teams,
            weapons=player_1_weapons,
            timers=player_1_timers,
        ),
        player_2=_seat_summary(
            seat=SEAT_PLAYER_2,
            deck=player_2_deck,
            deck_path=player_2_path,
            validation=player_2_validation,
            state=state,
            teams=player_2_teams,
            weapons=player_2_weapons,
            timers=player_2_timers,
        ),
        match_result=result,
    )


def default_full_loop_actions() -> tuple[DraftAction, ...]:
    raw_actions = (
        (SEAT_PLAYER_1, ACTION_BAN_CHARACTER, "test_p2_char_12"),
        (SEAT_PLAYER_2, ACTION_BAN_CHARACTER, "test_p1_char_12"),
        (SEAT_PLAYER_1, ACTION_BAN_CHARACTER, "test_p2_char_11"),
        (SEAT_PLAYER_2, ACTION_BAN_CHARACTER, "test_p1_char_11"),
        (SEAT_PLAYER_1, ACTION_PICK_CHARACTER, "test_p1_char_01"),
        (SEAT_PLAYER_2, ACTION_PICK_CHARACTER, "test_p2_char_01"),
        (SEAT_PLAYER_2, ACTION_PICK_CHARACTER, "test_p2_char_02"),
        (SEAT_PLAYER_1, ACTION_PICK_CHARACTER, "test_p1_char_02"),
        (SEAT_PLAYER_1, ACTION_PICK_CHARACTER, "test_p1_char_03"),
        (SEAT_PLAYER_2, ACTION_PICK_CHARACTER, "test_p2_char_03"),
        (SEAT_PLAYER_2, ACTION_PICK_CHARACTER, "test_p2_char_04"),
        (SEAT_PLAYER_1, ACTION_PICK_CHARACTER, "test_p1_char_04"),
        (SEAT_PLAYER_1, ACTION_BAN_CHARACTER, "test_p2_char_10"),
        (SEAT_PLAYER_2, ACTION_PICK_CHARACTER, "test_p2_char_05"),
        (SEAT_PLAYER_2, ACTION_BAN_CHARACTER, "test_p1_char_10"),
        (SEAT_PLAYER_1, ACTION_PICK_CHARACTER, "test_p1_char_05"),
        (SEAT_PLAYER_1, ACTION_PICK_CHARACTER, "test_p1_char_06"),
        (SEAT_PLAYER_2, ACTION_PICK_CHARACTER, "test_p2_char_06"),
        (SEAT_PLAYER_2, ACTION_PICK_CHARACTER, "test_p2_char_07"),
        (SEAT_PLAYER_1, ACTION_PICK_CHARACTER, "test_p1_char_07"),
        (SEAT_PLAYER_1, ACTION_PICK_CHARACTER, "test_p1_char_08"),
        (SEAT_PLAYER_2, ACTION_PICK_CHARACTER, "test_p2_char_08"),
    )
    return tuple(
        DraftAction(
            seat=seat,
            action_type=action_type,
            character_id=character_id,
            action_id=f"full-loop-smoke-{index}",
            sequence=index,
        )
        for index, (seat, action_type, character_id) in enumerate(raw_actions, start=1)
    )


def format_smoke_report(report: PvpFullLoopSmokeReport) -> str:
    player_1 = report.player_1
    player_2 = report.player_2
    result = report.match_result
    return "\n".join(
        (
            f"PvP full-loop smoke: {report.scenario_name}",
            f"Decks: {player_1.deck_name} vs {player_2.deck_name}",
            (
                "Validation: "
                f"{SEAT_PLAYER_1}={player_1.validation_status}, "
                f"{SEAT_PLAYER_2}={player_2.validation_status}"
            ),
            (
                "Schedule/actions: "
                f"{report.schedule_steps_count} steps, {report.action_count} actions"
            ),
            (
                f"{SEAT_PLAYER_1}: "
                f"bans={len(player_1.banned_character_ids)}, "
                f"picks={len(player_1.picked_character_ids)}, "
                f"teams={_compact_teams(player_1.teams)}, "
                f"weapon_assignments={len(player_1.weapons.assignments)}, "
                f"timer={player_1.timer_total_seconds}s"
            ),
            (
                f"{SEAT_PLAYER_2}: "
                f"bans={len(player_2.banned_character_ids)}, "
                f"picks={len(player_2.picked_character_ids)}, "
                f"teams={_compact_teams(player_2.teams)}, "
                f"weapon_assignments={len(player_2.weapons.assignments)}, "
                f"timer={player_2.timer_total_seconds}s"
            ),
            (
                "Result: "
                f"status={result.status}, winner={result.winner_seat}, "
                f"diff={result.seconds_difference}s"
            ),
            f"State hash: {report.state_hash}",
        )
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the backend-only PvP v0 full-loop fixture smoke.",
    )
    parser.add_argument("--json", action="store_true", help="Print structured JSON.")
    args = parser.parse_args(argv)
    try:
        report = run_default_full_loop_smoke()
    except Exception as exc:
        print(f"PvP full-loop smoke failed: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(format_smoke_report(report))
    return 0


def _seat_summary(
    *,
    seat: str,
    deck: DraftDeck,
    deck_path: Path,
    validation: DeckValidationReport,
    state: DraftSessionState,
    teams: PlayerTeamAssignment,
    weapons: PlayerWeaponAssignment,
    timers: PlayerMatchTimers,
) -> PvpSeatSmokeSummary:
    return PvpSeatSmokeSummary(
        seat=seat,
        nickname=deck.player.nickname,
        deck_name=deck.deck_name,
        deck_path=str(deck_path),
        validation_status=validation.status,
        banned_character_ids=state.banned_character_ids_for(seat),
        picked_character_ids=state.picked_character_ids_for(seat),
        teams=teams,
        weapons=weapons,
        timer_total_seconds=timers.total_elapsed_seconds,
        weapon_stack_usage=_weapon_stack_usage(weapons),
    )


def _team_assignment(seat: str, character_ids: tuple[str, ...]) -> PlayerTeamAssignment:
    return PlayerTeamAssignment(
        seat=seat,
        teams=(
            TeamAssignment(team_index=0, character_ids=character_ids[:4]),
            TeamAssignment(team_index=1, character_ids=character_ids[4:8]),
        ),
    )


def _weapon_assignment_for(
    state: DraftSessionState,
    teams: PlayerTeamAssignment,
) -> PlayerWeaponAssignment:
    deck = state.deck_for(teams.seat)
    assignments: list[CharacterWeaponAssignment] = []
    for team in teams.teams:
        for character_id in team.character_ids:
            character = deck.character_by_id[character_id]
            stack_key = _stack_key_for_weapon_type(deck, character.weapon_type)
            assignments.append(
                CharacterWeaponAssignment(
                    character_id=character_id,
                    weapon_stack_key=stack_key,
                )
            )
    return PlayerWeaponAssignment(seat=teams.seat, assignments=tuple(assignments))


def _stack_key_for_weapon_type(deck: DraftDeck, weapon_type: str) -> str:
    normalized = weapon_type.strip().casefold()
    for stack in deck.weapons:
        if stack.weapon_type.strip().casefold() == normalized:
            return stack.stack_key
    raise PvpFullLoopSmokeError(f"No weapon stack for weapon type {weapon_type!r}.")


def _weapon_stack_usage(assignment: PlayerWeaponAssignment) -> dict[str, int]:
    usage: dict[str, int] = {}
    for item in assignment.assignments:
        usage[item.weapon_stack_key] = usage.get(item.weapon_stack_key, 0) + 1
    return usage


def _compact_teams(assignment: PlayerTeamAssignment) -> str:
    return ",".join(str(len(team.character_ids)) for team in assignment.teams)


def _require_ready_deck(seat: str, report: DeckValidationReport) -> None:
    if not report.ready:
        raise PvpFullLoopSmokeError(
            f"{seat} deck validation failed: {list(report.issue_codes())}"
        )


def _require_ready_report(label: str, report: Any) -> None:
    if not report.ready:
        raise PvpFullLoopSmokeError(f"{label} failed: {list(report.issue_codes())}")


def _require_complete_pick_counts(state: DraftSessionState) -> None:
    if not state.is_complete:
        raise PvpFullLoopSmokeError("Draft did not complete.")
    if len(state.player_1_picked_character_ids) != 8:
        raise PvpFullLoopSmokeError("player_1 did not end with 8 picks.")
    if len(state.player_2_picked_character_ids) != 8:
        raise PvpFullLoopSmokeError("player_2 did not end with 8 picks.")
    if len(state.player_1_banned_character_ids) != 3:
        raise PvpFullLoopSmokeError("player_1 did not end with 3 bans.")
    if len(state.player_2_banned_character_ids) != 3:
        raise PvpFullLoopSmokeError("player_2 did not end with 3 bans.")


if __name__ == "__main__":
    raise SystemExit(main())
